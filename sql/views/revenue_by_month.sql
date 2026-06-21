CREATE OR REPLACE VIEW revenue_by_month AS
SELECT
    order_month,
    COUNT(DISTINCT order_id)    AS order_count,
    COUNT(DISTINCT user_id)     AS unique_customers,
    ROUND(SUM(total_amount), 2) AS total_revenue,
    ROUND(AVG(total_amount), 2) AS avg_order_value,
    ROUND(MAX(total_amount), 2) AS max_order_value,
    ROUND(MIN(total_amount), 2) AS min_order_value
FROM orders
GROUP BY order_month
ORDER BY order_month
