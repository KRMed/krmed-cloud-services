"""Unsloth QLoRA trainer (Phase 5C).

Fills the Trainer seam from executor.py with a real 4-bit QLoRA fine-tune built
on Unsloth. This is the only GPU-bound code in the worker, and it targets the
Blackwell / sm_120 stack pinned in requirements-gpu.txt. CUDA, torch,
bitsandbytes and Unsloth are imported lazily inside train() so the module stays
importable (and its pure helpers stay unit testable) on a machine without the
GPU stack installed.

Dataset contract (v1): the dataset must expose a "text" column holding the
formatted training string, the TRL/Unsloth SFT default. Instruction/response
templating is out of scope for v1 and rejected with a clear error, surfaced via
job status the same way unsupported formats are.

The adapter (adapter_config.json + adapter_model.safetensors) is written to
output_dir; the executor uploads exactly that directory to Garage, so trainer
state and intermediate checkpoints are kept out of it.
"""

import logging
import tempfile
from pathlib import Path
from typing import Callable

from shared.schema.job import Job

logger = logging.getLogger("crucible.worker.trainer")

# Conservative default context length; 16GB VRAM with QLoRA handles this for the
# 7-14B models the guardrail permits. Not a user hyperparameter in v1.
DEFAULT_MAX_SEQ_LENGTH = 2048

# Standard QLoRA target modules (attention + MLP projections).
TARGET_MODULES = (
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
)

# Fixed seed for reproducible adapters (Unsloth convention).
SEED = 3407

# The v1 dataset must carry the formatted training text in this column.
TEXT_FIELD = "text"

_FORMAT_BY_SUFFIX = {
    "csv": "csv",
    "json": "json",
    "jsonl": "json",
    "parquet": "parquet",
}


class TrainerError(RuntimeError):
    """Raised when a fine-tune cannot run (bad dataset, training failure)."""


def resolve_text_field(column_names: list[str]) -> str:
    """Return the training-text column, or raise if the v1 contract is unmet."""
    if TEXT_FIELD in column_names:
        return TEXT_FIELD
    raise TrainerError(
        f"dataset has no {TEXT_FIELD!r} column (found {sorted(column_names)}); "
        f"v1 requires a {TEXT_FIELD!r} column with the formatted training string"
    )


def dataset_load_spec(dataset_path: Path) -> tuple[str, list[str]]:
    """Resolve the Hugging Face loader format and file list for a local dataset.

    Pure (filesystem only) so it is testable without the GPU stack. Raises
    TrainerError for a missing path, an empty dataset, an unknown extension, or
    a mix of formats.
    """
    path = Path(dataset_path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file())
    elif path.is_file():
        files = [path]
    else:
        raise TrainerError(f"dataset path does not exist: {path}")

    if not files:
        raise TrainerError(f"no dataset files found in {path}")

    suffixes = {p.suffix.lower().lstrip(".") for p in files}
    unknown = suffixes - _FORMAT_BY_SUFFIX.keys()
    if unknown:
        raise TrainerError(
            f"unsupported dataset file extension(s) {sorted(unknown)} in {path}; "
            f"supported: {sorted(_FORMAT_BY_SUFFIX)}"
        )

    formats = {_FORMAT_BY_SUFFIX[s] for s in suffixes}
    if len(formats) != 1:
        raise TrainerError(
            f"dataset mixes multiple formats {sorted(formats)} in {path}; "
            f"v1 expects a single format"
        )

    return formats.pop(), [str(p) for p in files]


class UnslothQLoRATrainer:
    """Trainer seam implementation: 4-bit QLoRA fine-tune via Unsloth + TRL."""

    def __init__(self, max_seq_length: int = DEFAULT_MAX_SEQ_LENGTH) -> None:
        self._max_seq_length = max_seq_length

    def train(
        self,
        job: Job,
        model_path: Path,
        dataset_path: Path,
        output_dir: Path,
        heartbeat: Callable[[], None],
    ) -> None:
        # Imported here so the GPU stack is only required on the GPU box, and so
        # CUDA initialises after the launcher has pinned CUDA_VISIBLE_DEVICES.
        from datasets import load_dataset
        from transformers import TrainerCallback
        from trl import SFTConfig, SFTTrainer
        from unsloth import FastLanguageModel

        hp = job.hyperparameters
        fmt, files = dataset_load_spec(dataset_path)
        dataset = load_dataset(fmt, data_files=files, split="train")
        text_field = resolve_text_field(dataset.column_names)
        heartbeat()

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=str(model_path),
            max_seq_length=self._max_seq_length,
            load_in_4bit=True,  # QLoRA
        )
        model = FastLanguageModel.get_peft_model(
            model,
            r=hp.lora_rank,
            lora_alpha=hp.lora_alpha,
            target_modules=list(TARGET_MODULES),
            lora_dropout=0,
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=SEED,
            max_seq_length=self._max_seq_length,
        )
        heartbeat()

        class _HeartbeatCallback(TrainerCallback):
            def on_step_end(self, args, state, control, **kwargs):
                heartbeat()

        # Trainer state/logs go to a throwaway dir so output_dir holds only the
        # adapter; save_strategy="no" avoids writing optimizer checkpoints.
        with tempfile.TemporaryDirectory(prefix=f"crucible-train-{job.id}-") as state_dir:
            trainer = SFTTrainer(
                model=model,
                tokenizer=tokenizer,
                train_dataset=dataset,
                args=SFTConfig(
                    dataset_text_field=text_field,
                    max_seq_length=self._max_seq_length,
                    per_device_train_batch_size=hp.batch_size,
                    gradient_accumulation_steps=1,
                    num_train_epochs=hp.epochs,
                    learning_rate=hp.learning_rate,
                    logging_steps=1,
                    optim="adamw_8bit",
                    bf16=True,  # Blackwell supports bf16 natively
                    seed=SEED,
                    output_dir=state_dir,
                    save_strategy="no",
                    report_to="none",
                    dataset_num_proc=1,
                ),
                callbacks=[_HeartbeatCallback()],
            )

            logger.info(
                "starting QLoRA fine-tune for job %s (%d file(s), format %s)",
                job.id,
                len(files),
                fmt,
            )
            trainer.train()

        model.save_pretrained(str(output_dir))
        tokenizer.save_pretrained(str(output_dir))
        heartbeat()
        logger.info("fine-tune complete for job %s; adapter at %s", job.id, output_dir)
