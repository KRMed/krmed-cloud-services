# Garage Storage Conventions

## Bucket

Single bucket: `crucible`

All services use one bucket. Access is controlled by a single service credential
that covers all reads and writes.

## Prefix structure

```
crucible/
├── models/
│   └── {name}/
│       └── {version}/          # always a prefix, trailing slash implied
│           └── ...             # model weights, config, tokenizer files
│
├── datasets/
│   └── {name}/
│       └── {version}/          # multi-file dataset: prefix with trailing slash
│           └── ...
│       └── {version}.{ext}     # single-file dataset: object key (csv, json, parquet)
│
└── checkpoints/
    └── {job-id}/               # LoRA adapter output (adapter_config.json, adapter_model.safetensors)
        └── ...
```

## Key conventions

- `{name}` for models matches the `name` column in the `models` table (e.g. `mistral-7b-instruct`)
- `{version}` for HuggingFace models is the commit SHA from HF Hub, not a tag
- `{version}` for datasets is the SHA256 of the dataset content
- Model paths are always prefixes (`path_type = 'prefix'`)
- Dataset paths are a prefix for directories, an object key for single files (`path_type` varies)
- Checkpoint paths are always prefixes keyed by job UUID

## Multipart upload settings

| Setting | Value |
|---------|-------|
| Threshold | 8 MB (files below this are uploaded in a single request) |
| Chunk size | 512 MB |

## Environment variables

All services read credentials and endpoint from the environment. Never hardcode these.

| Variable | Purpose |
|----------|---------|
| `GARAGE_ENDPOINT` | Garage S3 API endpoint (e.g. `http://localhost:3900`) |
| `GARAGE_ACCESS_KEY` | S3 access key ID |
| `GARAGE_SECRET_KEY` | S3 secret access key |
| `GARAGE_BUCKET` | Bucket name (should be `crucible`) |
| `DATABASE_URL` | Postgres connection string |
