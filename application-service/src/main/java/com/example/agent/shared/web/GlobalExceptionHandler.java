package com.example.agent.shared.web;

import com.example.agent.shared.api.ApiResponse;
import com.example.agent.shared.api.FieldViolation;
import com.example.agent.shared.error.BusinessException;
import com.example.agent.shared.error.CommonErrorCode;
import com.example.agent.shared.error.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import java.util.ArrayList;
import java.util.List;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.validation.FieldError;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingRequestHeaderException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

/**
 * 全局异常处理器。
 *
 * <p>统一把异常转换为 {@link ApiResponse}，并遵循以下日志策略：</p>
 * <ul>
 *   <li>业务异常、参数校验失败：{@code WARN}，不打印堆栈</li>
 *   <li>404、405、415：{@code DEBUG}，不打印堆栈</li>
 *   <li>未预期异常：{@code ERROR}，只在此处打印一次完整堆栈</li>
 * </ul>
 *
 * <p>对外只返回通用提示，不返回异常消息、SQL、类名与堆栈。</p>
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiResponse<Object>> handleBusiness(BusinessException ex, HttpServletRequest request) {
        ErrorCode errorCode = ex.getErrorCode();
        log.warn("业务异常 code={} errorType={} message={} path={} requestId={}",
                errorCode.code(), errorCode.errorType(), ex.getMessage(),
                request.getRequestURI(), RequestContext.getRequestId());
        return ResponseEntity.status(errorCode.httpStatus())
                .body(ApiResponse.failure(errorCode, ex.getMessage(), ex.getPayload()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiResponse<List<FieldViolation>>> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex, HttpServletRequest request) {
        List<FieldViolation> violations = new ArrayList<>();
        for (FieldError fieldError : ex.getBindingResult().getFieldErrors()) {
            violations.add(new FieldViolation(fieldError.getField(), fieldError.getDefaultMessage()));
        }
        ex.getBindingResult().getGlobalErrors()
                .forEach(error -> violations.add(new FieldViolation(error.getObjectName(), error.getDefaultMessage())));
        return validationFailure(violations, request);
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ApiResponse<List<FieldViolation>>> handleHandlerMethodValidation(
            HandlerMethodValidationException ex, HttpServletRequest request) {
        List<FieldViolation> violations = ex.getParameterValidationResults().stream()
                .flatMap(result -> {
                    String parameterName = result.getMethodParameter().getParameterName();
                    String field = parameterName == null ? "parameter" : parameterName;
                    return result.getResolvableErrors().stream()
                            .map(error -> new FieldViolation(field, error.getDefaultMessage()));
                })
                .toList();
        return validationFailure(violations, request);
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ApiResponse<List<FieldViolation>>> handleConstraintViolation(
            ConstraintViolationException ex, HttpServletRequest request) {
        List<FieldViolation> violations = ex.getConstraintViolations().stream()
                .map(violation -> new FieldViolation(
                        violation.getPropertyPath().toString(), violation.getMessage()))
                .toList();
        return validationFailure(violations, request);
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ApiResponse<Void>> handleMissingParameter(
            MissingServletRequestParameterException ex, HttpServletRequest request) {
        String message = "缺少参数: " + ex.getParameterName();
        log.debug("缺少请求参数 path={} requestId={} parameter={}",
                request.getRequestURI(), RequestContext.getRequestId(), ex.getParameterName());
        return failure(CommonErrorCode.PARAM_MISSING, message);
    }

    @ExceptionHandler(MissingRequestHeaderException.class)
    public ResponseEntity<ApiResponse<Void>> handleMissingHeader(
            MissingRequestHeaderException ex, HttpServletRequest request) {
        String message = "缺少请求头: " + ex.getHeaderName();
        log.debug("缺少请求头 path={} requestId={} header={}",
                request.getRequestURI(), RequestContext.getRequestId(), ex.getHeaderName());
        return failure(CommonErrorCode.PARAM_MISSING, message);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiResponse<Void>> handleTypeMismatch(
            MethodArgumentTypeMismatchException ex, HttpServletRequest request) {
        String message = "参数类型不正确: " + ex.getName();
        log.debug("参数类型不正确 path={} requestId={} parameter={}",
                request.getRequestURI(), RequestContext.getRequestId(), ex.getName());
        return failure(CommonErrorCode.PARAM_TYPE_MISMATCH, message);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiResponse<Void>> handleUnreadableBody(
            HttpMessageNotReadableException ex, HttpServletRequest request) {
        log.debug("请求体解析失败 path={} requestId={}", request.getRequestURI(), RequestContext.getRequestId());
        return failure(CommonErrorCode.REQUEST_BODY_INVALID, CommonErrorCode.REQUEST_BODY_INVALID.message());
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<ApiResponse<Void>> handleNoResource(
            NoResourceFoundException ex, HttpServletRequest request) {
        log.debug("资源不存在 path={} requestId={}", request.getRequestURI(), RequestContext.getRequestId());
        return failure(CommonErrorCode.RESOURCE_NOT_FOUND, CommonErrorCode.RESOURCE_NOT_FOUND.message());
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ApiResponse<Void>> handleMethodNotSupported(
            HttpRequestMethodNotSupportedException ex, HttpServletRequest request) {
        log.debug("请求方法不支持 path={} method={} requestId={}",
                request.getRequestURI(), ex.getMethod(), RequestContext.getRequestId());
        return failure(CommonErrorCode.METHOD_NOT_ALLOWED, CommonErrorCode.METHOD_NOT_ALLOWED.message());
    }

    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    public ResponseEntity<ApiResponse<Void>> handleMediaTypeNotSupported(
            HttpMediaTypeNotSupportedException ex, HttpServletRequest request) {
        log.debug("请求内容类型不支持 path={} requestId={}",
                request.getRequestURI(), RequestContext.getRequestId());
        return failure(CommonErrorCode.MEDIA_TYPE_NOT_SUPPORTED, CommonErrorCode.MEDIA_TYPE_NOT_SUPPORTED.message());
    }

    @ExceptionHandler(AuthenticationException.class)
    public ResponseEntity<ApiResponse<Void>> handleAuthentication(
            AuthenticationException ex, HttpServletRequest request) {
        log.warn("认证失败 path={} requestId={} reason={}",
                request.getRequestURI(), RequestContext.getRequestId(), ex.getClass().getSimpleName());
        return failure(CommonErrorCode.UNAUTHORIZED, CommonErrorCode.UNAUTHORIZED.message());
    }

    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<ApiResponse<Void>> handleAccessDenied(
            AccessDeniedException ex, HttpServletRequest request) {
        log.warn("权限不足 path={} requestId={}", request.getRequestURI(), RequestContext.getRequestId());
        return failure(CommonErrorCode.FORBIDDEN, CommonErrorCode.FORBIDDEN.message());
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<Void>> handleUnexpected(Exception ex, HttpServletRequest request) {
        log.error("未处理异常 path={} requestId={}", request.getRequestURI(), RequestContext.getRequestId(), ex);
        return failure(CommonErrorCode.SYSTEM_ERROR, CommonErrorCode.SYSTEM_ERROR.message());
    }

    private ResponseEntity<ApiResponse<List<FieldViolation>>> validationFailure(
            List<FieldViolation> violations, HttpServletRequest request) {
        log.warn("参数校验失败 path={} requestId={} violations={}",
                request.getRequestURI(), RequestContext.getRequestId(), violations);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiResponse.failure(CommonErrorCode.PARAM_INVALID,
                        CommonErrorCode.PARAM_INVALID.message(), violations));
    }

    private ResponseEntity<ApiResponse<Void>> failure(ErrorCode errorCode, String message) {
        return ResponseEntity.status(errorCode.httpStatus())
                .body(ApiResponse.failure(errorCode, message));
    }
}
