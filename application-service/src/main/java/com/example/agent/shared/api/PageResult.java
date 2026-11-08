package com.example.agent.shared.api;

import java.util.List;

/**
 * 分页结果。
 *
 * <p>{@code list} 为空时返回空集合，不返回 {@code null}，避免调用方做额外判空。</p>
 *
 * @param list  当前页数据
 * @param total 总条数
 * @param page  当前页码，从 1 开始
 * @param size  每页条数
 */
public record PageResult<T>(List<T> list, long total, int page, int size) {

    public PageResult {
        list = list == null ? List.of() : List.copyOf(list);
    }

    public static <T> PageResult<T> of(List<T> list, long total, PageQuery query) {
        return new PageResult<>(list, total, query.getPage(), query.getSize());
    }

    public static <T> PageResult<T> empty(PageQuery query) {
        return new PageResult<>(List.of(), 0, query.getPage(), query.getSize());
    }
}
