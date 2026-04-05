import type { Job } from '../schema/job';
import type { APIError } from './errors';

export interface JobResponse {
  data: Job | null;
  error: APIError | null;
}

export interface ListJobsSuccessResponse {
  data: Job[];
  total: number;
  limit: number;
  offset: number;
  error: null;
}

export interface ListJobsErrorResponse {
  error: APIError;
}

export type ListJobsResponse = ListJobsSuccessResponse | ListJobsErrorResponse;
