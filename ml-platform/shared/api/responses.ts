import type { Job } from '../schema/job';

export interface JobResponse {
  data: Job | null;
  error: string | null;
}

export interface ListJobsResponse {
  data: Job[];
  total: number;
  limit: number;
  offset: number;
  error: string | null;
}
