"""End-to-end QLoRA smoke test for the RTX 5060 Ti (Blackwell / sm_120).

CLAUDE.md requires a trivial end-to-end QLoRA run on the real card before
building anything on top of the fragile Blackwell CUDA/torch/bitsandbytes stack.
This is that gate: it loads a tiny model in 4-bit, attaches a LoRA adapter,
trains a handful of steps on an in-memory dataset, and saves the adapter. If it
finishes and writes adapter weights, the stack works on this card.

Run on the GPU box only, after installing requirements-gpu.txt:
    python scripts/qlora_smoke_test.py

Exit code 0 = PASS. Any exception = the stack is not usable yet; fix the pins
before locking exact versions in CLAUDE.md / requirements-gpu.txt.
"""

import sys
import tempfile
from pathlib import Path

# Small model so the smoke test is fast and fits any 16GB card with headroom.
SMOKE_MODEL = "unsloth/tinyllama-bnb-4bit"
MAX_SEQ_LENGTH = 512


def main() -> int:
    import torch
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastLanguageModel

    if not torch.cuda.is_available():
        print("FAIL: CUDA is not available to torch", file=sys.stderr)
        return 1

    name = torch.cuda.get_device_name(0)
    capability = torch.cuda.get_device_capability(0)
    print(f"device: {name} (sm_{capability[0]}{capability[1]}), torch {torch.__version__}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=SMOKE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=8,
        lora_alpha=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        use_gradient_checkpointing="unsloth",
        random_state=3407,
        max_seq_length=MAX_SEQ_LENGTH,
    )

    dataset = Dataset.from_dict(
        {"text": [f"Smoke test example number {i}." for i in range(16)]}
    )

    with tempfile.TemporaryDirectory() as out:
        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            args=SFTConfig(
                dataset_text_field="text",
                max_seq_length=MAX_SEQ_LENGTH,
                per_device_train_batch_size=2,
                gradient_accumulation_steps=1,
                max_steps=3,
                learning_rate=2e-4,
                logging_steps=1,
                optim="adamw_8bit",
                bf16=True,
                seed=3407,
                output_dir=out,
                save_strategy="no",
                report_to="none",
                dataset_num_proc=1,
            ),
        )
        trainer.train()

        adapter_dir = Path(out) / "adapter"
        model.save_pretrained(str(adapter_dir))
        weights = list(adapter_dir.glob("adapter_model.*"))
        if not weights:
            print("FAIL: no adapter weights were written", file=sys.stderr)
            return 1
        print(f"PASS: trained 3 steps and saved adapter ({weights[0].name})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
