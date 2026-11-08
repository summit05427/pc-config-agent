package com.example.agent.model.infrastructure;

import java.util.Collection;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 模型定价数据访问，SQL 见 {@code mapper/model/ModelPricingMapper.xml}。
 */
@Mapper
public interface ModelPricingMapper {

    /**
     * 按批次需要的 Provider 与模型键一次性读取全部定价版本，避免逐条查询。
     *
     * <p>两个条件分别用 {@code IN} 过滤，可能多取到「Provider 与模型键不属于同一组合」的行，
     * 由调用方按完整组合过滤；同一批次的价格版本数量有限，多取的成本低于 N+1。</p>
     *
     * @param providers  Provider 代码集合，不可为空
     * @param modelKeys  模型键集合，不可为空
     * @return 定价版本行，按 {@code effectiveFrom} 倒序
     */
    List<ModelPricingRow> findByModels(
            @Param("providers") Collection<String> providers,
            @Param("modelKeys") Collection<String> modelKeys);
}
