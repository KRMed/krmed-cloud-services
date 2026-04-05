export type ErrorCode =
  | 'JOB_NOT_FOUND'
  | 'INVALID_REQUEST'
  | 'UNSUPPORTED_DATASET_FORMAT'
  | 'MODEL_NOT_FOUND'
  | 'QUEUE_FULL'
  | 'INTERNAL_SERVER_ERROR';

export interface APIError {
  code: ErrorCode;
  message: string;
}
