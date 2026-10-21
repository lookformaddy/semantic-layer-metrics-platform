"""Default semantic model over a generic synthetic retail-style dataset.

Three entities — order (fact), customer, product — with declared
many-to-one joins from the fact. Metrics are defined once here; every
dashboard, API caller and notebook gets the same numbers because they
all compile through these definitions.
"""
from __future__ import annotations

from .catalog import SemanticCatalog
from .models import (Aggregation, Cardinality, Dimension, Entity, Join,
                     Metric, MetricStatus, SourceTable, Tier)

OWNER = "data-platform"


def build_default_catalog() -> SemanticCatalog:
    catalog = SemanticCatalog()

    catalog.add_table(SourceTable("orders", (
        "order_id", "customer_id", "product_id", "order_date", "status",
        "channel", "amount", "discount_amount", "quantity")))
    catalog.add_table(SourceTable("customers", (
        "customer_id", "customer_name", "region", "segment", "signup_date")))
    catalog.add_table(SourceTable("products", (
        "product_id", "product_name", "category", "unit_cost")))

    catalog.add_entity(Entity("order", "orders", "order_id", "One row per order."))
    catalog.add_entity(Entity("customer", "customers", "customer_id", "One row per customer."))
    catalog.add_entity(Entity("product", "products", "product_id", "One row per product."))

    for dim in (
        Dimension("order_date", "order", "order_date", "date", "Calendar date of the order.", is_time=True),
        Dimension("order_status", "order", "status", "string", "Order lifecycle status."),
        Dimension("order_channel", "order", "channel", "string", "Sales channel."),
        Dimension("customer_region", "customer", "region", "string", "Customer region."),
        Dimension("customer_segment", "customer", "segment", "string", "Customer segment."),
        Dimension("product_category", "product", "category", "string", "Product category."),
        Dimension("product_name", "product", "product_name", "string", "Product name."),
    ):
        catalog.add_dimension(dim)

    catalog.add_join(Join("order_customer", "order", "customer",
                          "customer_id", "customer_id", Cardinality.MANY_TO_ONE))
    catalog.add_join(Join("order_product", "order", "product",
                          "product_id", "product_id", Cardinality.MANY_TO_ONE))

    catalog.add_metrics([
        Metric("total_revenue", "order", Aggregation.SUM, "amount",
               label="Total Revenue", description="Sum of order amounts.",
               owner=OWNER, tier=Tier.GOLD, status=MetricStatus.CERTIFIED,
               tags=("revenue", "finance")),
        Metric("total_discount", "order", Aggregation.SUM, "discount_amount",
               label="Total Discount", description="Sum of discount amounts.",
               owner=OWNER, tier=Tier.SILVER, status=MetricStatus.CERTIFIED,
               tags=("revenue",)),
        Metric("order_count", "order", Aggregation.COUNT, "order_id",
               label="Order Count", description="Number of orders.",
               owner=OWNER, tier=Tier.GOLD, status=MetricStatus.CERTIFIED,
               tags=("volume",)),
        Metric("unique_customers", "order", Aggregation.COUNT_DISTINCT, "customer_id",
               label="Unique Customers", description="Distinct customers who ordered.",
               owner=OWNER, tier=Tier.GOLD, status=MetricStatus.CERTIFIED,
               tags=("customers", "volume")),
        Metric("average_order_value", "order", Aggregation.AVG, "amount",
               label="Average Order Value", description="Mean order amount.",
               owner=OWNER, tier=Tier.SILVER, status=MetricStatus.CERTIFIED,
               tags=("revenue",)),
        Metric("total_quantity", "order", Aggregation.SUM, "quantity",
               label="Total Quantity", description="Units sold.",
               owner=OWNER, tier=Tier.SILVER, status=MetricStatus.CERTIFIED,
               tags=("volume",)),
        Metric("discount_rate", "order", Aggregation.SUM, None,
               label="Discount Rate", description="Discount as a share of revenue.",
               owner=OWNER, tier=Tier.SILVER, status=MetricStatus.CERTIFIED,
               tags=("revenue",), numerator="total_discount", denominator="total_revenue"),
        Metric("customer_count", "customer", Aggregation.COUNT, "customer_id",
               label="Customer Count", description="Number of customers.",
               owner=OWNER, tier=Tier.SILVER, status=MetricStatus.CERTIFIED,
               tags=("customers",)),
        Metric("repeat_order_share", "order", Aggregation.AVG, "quantity",
               label="Repeat Order Share (experimental)",
               description="Experimental proxy metric, not yet certified.",
               owner=OWNER, tier=Tier.BRONZE, status=MetricStatus.DRAFT,
               tags=("experimental",)),
        Metric("legacy_gross_sales", "order", Aggregation.SUM, "amount",
               label="Legacy Gross Sales",
               description="Pre-2024 definition; superseded by total_revenue.",
               owner=OWNER, tier=Tier.BRONZE, status=MetricStatus.DEPRECATED,
               tags=("legacy",), replaced_by="total_revenue"),
    ])
    catalog.assert_valid()
    return catalog
