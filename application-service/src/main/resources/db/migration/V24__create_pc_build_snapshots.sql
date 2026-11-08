-- PC 配置方案快照：append-only，只新增不更新不删除，用于回溯求解输入与结论。
CREATE TABLE pc_build_snapshots (
    build_id                  uuid PRIMARY KEY,
    user_id                   uuid NOT NULL,
    parent_build_id           uuid NULL REFERENCES pc_build_snapshots (build_id),
    requirements_snapshot     jsonb NOT NULL,
    components                jsonb NOT NULL,
    total_price_fen           bigint NOT NULL CHECK (total_price_fen >= 0),
    budget_max_fen            bigint NULL CHECK (budget_max_fen IS NULL OR budget_max_fen >= 0),
    compatibility_report      jsonb NOT NULL,
    benchmark_snapshot        jsonb NOT NULL,
    offer_snapshot            jsonb NOT NULL,
    solver_version            varchar(32) NOT NULL,
    compatibility_rule_version varchar(32) NOT NULL,
    catalog_version           varchar(64) NOT NULL,
    created_at                timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE pc_build_snapshots IS 'PC 配置推荐方案快照，append-only';
COMMENT ON COLUMN pc_build_snapshots.user_id IS 'JWT sub（用户公开 ID），读取时必须校验归属';
COMMENT ON COLUMN pc_build_snapshots.total_price_fen IS '总价，单位：人民币分';
COMMENT ON COLUMN pc_build_snapshots.budget_max_fen IS '预算上限，单位：人民币分；为空表示无硬预算';
COMMENT ON COLUMN pc_build_snapshots.solver_version IS '求解器版本，用于判断历史结果是否可比较';

CREATE INDEX idx_pc_build_snapshots_user_created
    ON pc_build_snapshots (user_id, created_at DESC);

CREATE INDEX idx_pc_build_snapshots_parent
    ON pc_build_snapshots (parent_build_id);
