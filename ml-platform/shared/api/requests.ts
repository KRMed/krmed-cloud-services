import type { Hyperparameters, JobStatus } from '../schema/job';

export interface CreateJobRequest {
  base_model: string;
  dataset_path: string;
  hyperparameters: Hyperparameters;
}

export interface ListJobsParams {
  status?: JobStatus;
  limit?: number;
  offset?: number;
}
