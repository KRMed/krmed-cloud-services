# Garage Bucket Layout

Single bucket: `crucible`

## Prefix structure

```
crucible/
├── datasets/
│   └── {name}/
│       └── {sha256}/           # multi-file dataset: prefix with trailing slash
│           └── ...
│       └── {sha256}.{ext}      # single-file dataset: object key (csv, json, parquet)
│
└── checkpoints/
    └── {job-id}/
        └── ...                 # LoRA adapter files (adapter_config.json, adapter_model.safetensors)
```

Postgres backups (pg_dump) live in a separate bucket; see the database backup config, not this layout.

## Notes

- Garage holds only datasets and LoRA checkpoints. Base-model weights are NOT stored here —
  the worker downloads them from the Hugging Face Hub and caches them on the GPU box local HDD.
  The `models` table is an allow-list of HF repos, not a pointer into Garage.
- One bucket keeps access key policy simple - a single service credential covers all reads and writes.
- Dataset version is the SHA256 of content, making paths content-addressed and stable across re-uploads.
- Checkpoint path stored in Postgres as `checkpoints/{job-id}/` (prefix, not a single file —
  LoRA adapters are a directory of files).
- Worker writes checkpoints, backend reads paths. Neither service writes to the other's prefix.
- See `garage-conventions.md` for multipart upload settings and environment variable reference.
