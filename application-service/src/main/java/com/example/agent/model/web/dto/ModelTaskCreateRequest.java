package com.example.agent.model.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 创建运行时任务请求。
 *
 * @param threadId 会话线程标识，必填
 * @param model    单次覆盖的模型引用；为空表示使用会话默认或 Auto
 */
public record ModelTaskCreateRequest(
        @NotBlank(message = "threadId 不能为空")
        @Size(max = 128, message = "threadId 长度不能超过 128")
        String threadId,

        @Size(max = 64, message = "model 长度不能超过 64")
        String model) {
}
