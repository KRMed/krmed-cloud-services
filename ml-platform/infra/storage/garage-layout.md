# Garage Bucket Layout

Single bucket: `crucible`

## Prefix structure

```
crucible/
├── models/
│   └── {name}/                 # e.g. mistral-7b-instruct
│       └── {version}/          # HF commit SHA or arbitrary version string
│           └── ...             # model weights and config files
│
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

## Notes

- One bucket keeps access key policy simple - a single service credential covers all reads and writes.
- Model prefix: `models/{name}/{version}/` — version is HF Hub commit SHA for HF models.
- Dataset version is the SHA256 of content, making paths content-addressed and stable across re-uploads.
- Checkpoint path stored in Postgres as `checkpoints/{job-id}/` (prefix, not a single file —
  LoRA adapters are a directory of files).
- Worker writes checkpoints, backend reads paths. Neither service writes to the other's prefix.
- See `garage-conventions.md` for multipart upload settings and environment variable reference.
