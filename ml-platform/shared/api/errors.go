package api

type ErrorCode string

const (
	ErrJobNotFound          ErrorCode = "JOB_NOT_FOUND"
	ErrInvalidRequest       ErrorCode = "INVALID_REQUEST"
	ErrUnsupportedDataset   ErrorCode = "UNSUPPORTED_DATASET_FORMAT"
	ErrModelNotFound        ErrorCode = "MODEL_NOT_FOUND"
	ErrQueueFull            ErrorCode = "QUEUE_FULL"
	ErrInternalServer       ErrorCode = "INTERNAL_SERVER_ERROR"
	ErrUnauthorized         ErrorCode = "UNAUTHORIZED"
)

type APIError struct {
	Code    ErrorCode `json:"code"`
	Message string    `json:"message"`
}

func (e *APIError) Error() string {
	return string(e.Code) + ": " + e.Message
}
