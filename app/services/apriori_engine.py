import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder

from app.schemas.api import AprioriResponse, AprioriRuleItem
from app.services.external_apis import fetch_groceries_transactions


def mine_product_associations(
    min_support: float = 0.015,
    min_confidence: float = 0.25,
    top_k: int = 10,
) -> AprioriResponse:
    """Run Apriori market-basket analysis on real supermarket transactions to guide expiry bundles."""
    transactions, source = fetch_groceries_transactions()
    if not transactions:
        return AprioriResponse(transactions_analyzed=0, dataset_source=source, rules=[])

    # Cap at 5,000 baskets for sub-second interactive API latency while preserving real distributions
    sample_txns = transactions[:5000]
    encoder = TransactionEncoder()
    encoded_ary = encoder.fit(sample_txns).transform(sample_txns)
    basket_df = pd.DataFrame(encoded_ary, columns=encoder.columns_)

    frequent_itemsets = apriori(basket_df, min_support=min_support, use_colnames=True)
    if frequent_itemsets.empty:
        return AprioriResponse(
            transactions_analyzed=len(sample_txns),
            dataset_source=source,
            rules=[],
        )

    rules_df = association_rules(frequent_itemsets, metric="confidence", min_threshold=min_confidence)
    if rules_df.empty:
        return AprioriResponse(
            transactions_analyzed=len(sample_txns),
            dataset_source=source,
            rules=[],
        )

    rules_df = rules_df.sort_values(by=["lift", "confidence"], ascending=False).head(top_k)

    results: list[AprioriRuleItem] = []
    for _, row in rules_df.iterrows():
        antecedents = sorted(list(row["antecedents"]))
        consequents = sorted(list(row["consequents"]))
        ant_str = ", ".join(antecedents)
        con_str = ", ".join(consequents)
        results.append(
            AprioriRuleItem(
                antecedents=antecedents,
                consequents=consequents,
                support=round(float(row["support"]), 4),
                confidence=round(float(row["confidence"]), 4),
                lift=round(float(row["lift"]), 3),
                bundle_suggestion=(
                    f"Co-promote [{ant_str}] with near-expiry [{con_str}] "
                    f"(Lift {row['lift']:.2f}x) to accelerate sell-through"
                ),
            )
        )

    return AprioriResponse(
        transactions_analyzed=len(sample_txns),
        dataset_source=source,
        rules=results,
    )
