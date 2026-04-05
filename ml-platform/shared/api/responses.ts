import type { Job } from '../schema/job';
import type { APIError } from './errors';

export interface JobResponse {
  data: Job | null;
  error: APIError | null;
}

export interface ListJobsResponse {
  data: Job[];
  total: number;
  limit: number;
  offset: number;
  error: APIError | null;
}
