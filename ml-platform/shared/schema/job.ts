export type JobStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface Hyperparameters {
  learning_rate: number;
  epochs: number;
  batch_size: number;
  lora_rank: number;
  lora_alpha: number;
}

export interface Job {
  id: string;
  status: JobStatus;
  base_model: string;
  dataset_path: string;
  hyperparameters: Hyperparameters;
  checkpoint_path: string | null;
  error_message: string | null;
  created_at: string; // ISO 8601
  updated_at: string; // ISO 8601
}
