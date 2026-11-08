package com.example.agent.shared.api;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.Getter;
import lombok.Setter;

/**
 * 分页查询参数。
 *
 * <p>默认第 1 页、每页 20 条，单页最多 100 条。超过上限直接返回参数错误，不做静默截断，
 * 避免调用方误以为拿到了完整数据。</p>
 */
@Getter
@Setter
public class PageQuery {

    public static final int DEFAULT_PAGE = 1;
    public static final int DEFAULT_SIZE = 20;
    public static final int MAX_SIZE = 100;

    @Min(value = 1, message = "page 必须大于等于 1")
    private int page = DEFAULT_PAGE;

    @Min(value = 1, message = "size 必须大于等于 1")
    @Max(value = MAX_SIZE, message = "size 不能超过 {value}")
    private int size = DEFAULT_SIZE;

    /**
     * 计算数据库分页偏移量，使用 long 避免大页码下的整型溢出。
     *
     * @return 偏移量
     */
    public long offset() {
        return (long) (page - 1) * size;
    }
}
