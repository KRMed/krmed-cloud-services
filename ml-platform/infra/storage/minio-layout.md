# Garage Bucket Layout

Single bucket: `crucible`

## Prefix structure

```
crucible/
├── models/
│   └── {hf-model-id}/          # e.g. meta-llama/Llama-3.2-1B
│       └── {revision}/         # git commit SHA from HF Hub
│           └── ...             # model weights and config files
│
├── datasets/
│   └── {job-id}/
│       └── {filename}          # original upload (CSV, JSON, or Parquet)
│
└── checkpoints/
    └── {job-id}/
        └── ...                 # LoRA adapter files (adapter_config.json, adapter_model.safetensors)
```

## Notes

- One bucket keeps access key policy simple - a single service credential covers all reads and writes.
- Model cache is keyed by `{hf-model-id}/{revision}` so a re-run of the same model+revision hits
  the cache without re-downloading. Revision is the HF Hub commit SHA, not a tag, to avoid
  ambiguity (tags can be moved).
- Dataset path stored in Postgres as `datasets/{job-id}/{filename}` (relative to bucket root).
- Checkpoint path stored in Postgres as `checkpoints/{job-id}/` (prefix, not a single file —
  LoRA adapters are a directory of files).
- Worker writes checkpoints, backend reads paths. Neither service writes to the other's prefix.
