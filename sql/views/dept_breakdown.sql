CREATE OR REPLACE VIEW dept_breakdown AS
SELECT
    p.department,
    COUNT(DISTINCT oi.order_id)   AS orders_containing,
    COUNT(oi.id)                  AS total_items_ordered,
    COUNT(DISTINCT oi.product_id) AS unique_products,
    SUM(oi.reordered)             AS total_reorders,
    ROUND(
        CAST(SUM(oi.reordered) AS DOUBLE)
        / NULLIF(COUNT(oi.id), 0) * 100,
        1
    )                             AS reorder_rate_pct
FROM order_items oi
JOIN products p ON oi.product_id = CAST(p.product_id AS BIGINT)
GROUP BY p.department
ORDER BY total_items_ordered DESC
