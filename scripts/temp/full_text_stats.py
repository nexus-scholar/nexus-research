#!/usr/bin/env python
"""
Temporary analysis script for full_text_extraction.json.

Generates:
- results/full_text_stats.json (machine-readable)
- results/full_text_stats.md (human-readable summary)
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

import matplotlib.pyplot as plt


NR_TOKENS = {"nr", "n/a", "na", "none", "null", ""}
NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _normalize_str(value: str) -> str:
    return " ".join(value.strip().lower().split())


def classify_value(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, str):
        if _normalize_str(value) in NR_TOKENS:
            return "nr"
        return "value"
    if isinstance(value, list):
        return "empty_list" if len(value) == 0 else "value"
    if isinstance(value, dict):
        return "empty_object" if len(value) == 0 else "value"
    return "value"


def parse_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = NUM_RE.search(value.replace(",", ""))
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def summarize_numeric(values: list[float]) -> dict[str, Any]:
    if not values:
        return {}
    values_sorted = sorted(values)
    result = {
        "count": len(values_sorted),
        "min": values_sorted[0],
        "max": values_sorted[-1],
        "mean": statistics.mean(values_sorted),
        "median": statistics.median(values_sorted),
    }
    if len(values_sorted) > 1:
        result["stdev"] = statistics.stdev(values_sorted)
    scale = {
        "lte_1": sum(1 for v in values_sorted if v <= 1.0),
        "gt_1": sum(1 for v in values_sorted if v > 1.0),
        "gt_1_le_100": sum(1 for v in values_sorted if 1.0 < v <= 100.0),
    }
    result["scale_hint"] = scale
    return result


def normalize_percentage(values: list[float]) -> dict[str, Any]:
    normalized = []
    outliers = []
    for value in values:
        if value <= 1.0:
            normalized.append(value)
        elif value <= 100.0:
            normalized.append(value / 100.0)
        else:
            outliers.append(value)
    return {
        "normalized": normalized,
        "outliers": outliers,
        "counts": {
            "lte_1": sum(1 for v in values if v <= 1.0),
            "gt_1_le_100": sum(1 for v in values if 1.0 < v <= 100.0),
            "gt_100": sum(1 for v in values if v > 100.0),
        },
    }


def save_bar_chart(
    title: str,
    items: list[tuple[str, int]],
    output_path: Path,
    max_items: int = 12,
) -> None:
    if not items:
        return
    labels = [name for name, _ in items[:max_items]]
    counts = [count for _, count in items[:max_items]]
    plt.figure(figsize=(8, 4.8))
    plt.barh(labels[::-1], counts[::-1], color="#4c78a8")
    plt.title(title)
    plt.xlabel("Count")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def save_histogram(
    title: str,
    values: list[float],
    output_path: Path,
    bins: int = 20,
    log_scale: bool = False,
    xlabel: str | None = None,
) -> None:
    if not values:
        return
    plt.figure(figsize=(6.5, 4.5))
    plt.hist(values, bins=bins, color="#72b7b2", edgecolor="white")
    plt.title(title)
    if xlabel:
        plt.xlabel(xlabel)
    if log_scale:
        plt.xscale("log")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def save_scatter(
    title: str,
    x_values: list[float],
    y_values: list[float],
    output_path: Path,
    x_log: bool = False,
    xlabel: str | None = None,
    ylabel: str | None = None,
) -> None:
    if not x_values or not y_values:
        return
    plt.figure(figsize=(6, 4.5))
    plt.scatter(x_values, y_values, alpha=0.6, s=16, color="#f58518")
    plt.title(title)
    if xlabel:
        plt.xlabel(xlabel)
    if ylabel:
        plt.ylabel(ylabel)
    if x_log:
        plt.xscale("log")
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()


def normalize_task_type(value: str) -> str:
    normalized = _normalize_str(value)
    mapping = {
        "classification": "classification",
        "classification task": "classification",
        "detection": "detection",
        "object detection": "detection",
        "segmentation": "segmentation",
        "severity estimation": "severity estimation",
    }
    return mapping.get(normalized, normalized)


def rankdata(values: list[float]) -> list[float]:
    sorted_vals = sorted((v, i) for i, v in enumerate(values))
    ranks = [0.0] * len(values)
    i = 0
    while i < len(sorted_vals):
        j = i
        while j < len(sorted_vals) and sorted_vals[j][0] == sorted_vals[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2.0
        for k in range(i, j):
            ranks[sorted_vals[k][1]] = avg_rank
        i = j
    return ranks


def pearson_corr(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(y) < 3 or len(x) != len(y):
        return None
    return statistics.correlation(x, y)


def spearman_corr(x: list[float], y: list[float]) -> float | None:
    if len(x) < 3 or len(y) < 3 or len(x) != len(y):
        return None
    return statistics.correlation(rankdata(x), rankdata(y))


def flatten_list(values: list[Any]) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    normalized = _normalize_str(item)
                    if normalized and normalized not in NR_TOKENS:
                        flattened.append(normalized)
        elif isinstance(value, str):
            normalized = _normalize_str(value)
            if normalized and normalized not in NR_TOKENS:
                flattened.append(normalized)
    return flattened


def load_schema(schema_path: Path) -> dict[str, str]:
    data = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    fields = data.get("fields", []) if isinstance(data, dict) else []
    return {field.get("id"): field.get("type", "") for field in fields if isinstance(field, dict)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze full-text extraction output.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("results/full_text_extraction.json"),
        help="Path to full_text_extraction.json",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("full_text_extraction_schema.yaml"),
        help="Schema YAML used for extraction.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="Directory for summary outputs.",
    )
    parser.add_argument("--top-k", type=int, default=12, help="Top-K for frequency tables.")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    schema_types = load_schema(args.schema) if args.schema.exists() else {}

    total_papers = len(data)
    field_counts: dict[str, Counter] = defaultdict(Counter)
    list_frequencies: dict[str, Counter] = defaultdict(Counter)
    numeric_metrics: dict[str, list[float]] = defaultdict(list)
    group_coverage: Counter = Counter()
    token_estimates: dict[str, list[int]] = defaultdict(list)

    task_types: Counter = Counter()
    dataset_names: Counter = Counter()
    dataset_domains: Counter = Counter()
    dataset_samples: list[float] = []
    dataset_classes: list[float] = []
    architecture_names: Counter = Counter()
    pretrained_counts: Counter = Counter()
    optimizer_counts: Counter = Counter()
    regularization_counts: Counter = Counter()
    learning_rates: list[float] = []
    epochs: list[float] = []
    batch_sizes: list[float] = []

    accuracy_samples_pairs: list[tuple[float, float]] = []
    accuracy_model_size_pairs: list[tuple[float, float]] = []
    accuracy_latency_pairs: list[tuple[float, float]] = []

    for item in data:
        extraction = item.get("extraction", {}) if isinstance(item, dict) else {}
        meta = item.get("meta", {}) if isinstance(item, dict) else {}
        groups = meta.get("groups", {}) if isinstance(meta, dict) else {}
        if isinstance(groups, dict):
            for group_id, group_meta in groups.items():
                group_coverage[group_id] += 1
                if isinstance(group_meta, dict):
                    token_estimate = group_meta.get("token_estimate")
                    if isinstance(token_estimate, int):
                        token_estimates[group_id].append(token_estimate)

        for field_id, field_type in schema_types.items():
            value = extraction.get(field_id)
            classification = classify_value(value)
            field_counts[field_id][classification] += 1

            if field_type.startswith("list"):
                list_frequencies[field_id].update(flatten_list([value] if value is not None else []))

        if isinstance(extraction.get("task_type"), str):
            task_types[normalize_task_type(extraction["task_type"])] += 1

        # datasets
        paper_samples: list[float] = []
        datasets = extraction.get("datasets")
        if isinstance(datasets, list):
            for dataset in datasets:
                if not isinstance(dataset, dict):
                    continue
                name = dataset.get("name")
                if isinstance(name, str):
                    dataset_names[_normalize_str(name)] += 1
                domain = dataset.get("domain")
                if isinstance(domain, str):
                    dataset_domains[_normalize_str(domain)] += 1
                samples = parse_number(dataset.get("samples"))
                if samples is not None:
                    dataset_samples.append(samples)
                    paper_samples.append(samples)
                classes = parse_number(dataset.get("classes"))
                if classes is not None:
                    dataset_classes.append(classes)

        # architectures
        architectures = extraction.get("architectures")
        if isinstance(architectures, list):
            for arch in architectures:
                if not isinstance(arch, dict):
                    continue
                name = arch.get("architecture")
                if isinstance(name, str):
                    architecture_names[_normalize_str(name)] += 1
                pretrained = arch.get("pretrained")
                if isinstance(pretrained, bool):
                    pretrained_counts[str(pretrained).lower()] += 1

        # training details
        training = extraction.get("training_details")
        if isinstance(training, dict):
            optimizer = training.get("optimizer")
            if isinstance(optimizer, str):
                optimizer_counts[_normalize_str(optimizer)] += 1
            regularization = training.get("regularization")
            if isinstance(regularization, str):
                regularization_counts[_normalize_str(regularization)] += 1
            lr = parse_number(training.get("learning_rate"))
            if lr is not None:
                learning_rates.append(lr)
            ep = parse_number(training.get("epochs"))
            if ep is not None:
                epochs.append(ep)
            bs = parse_number(training.get("batch_size"))
            if bs is not None:
                batch_sizes.append(bs)

        # evaluation metrics
        evaluation = extraction.get("evaluation_metrics")
        accuracy_value = None
        if isinstance(evaluation, dict):
            for metric in ["accuracy", "precision", "recall", "f1_score", "mAP", "IoU", "cross_dataset"]:
                value = parse_number(evaluation.get(metric))
                if value is not None:
                    numeric_metrics[f"evaluation_metrics.{metric}"].append(value)
                if metric == "accuracy":
                    accuracy_value = value

        # inference performance
        perf = extraction.get("inference_performance")
        if isinstance(perf, dict):
            for metric in ["latency_ms", "throughput_fps", "model_size_mb", "memory_usage_mb"]:
                value = parse_number(perf.get(metric))
                if value is not None:
                    numeric_metrics[f"inference_performance.{metric}"].append(value)

        if accuracy_value is not None:
            normalized_accuracy = normalize_percentage([accuracy_value])["normalized"]
            accuracy = normalized_accuracy[0] if normalized_accuracy else None
            if accuracy is not None:
                if paper_samples:
                    accuracy_samples_pairs.append((max(paper_samples), accuracy))
                model_size = None
                if isinstance(perf, dict):
                    model_size = parse_number(perf.get("model_size_mb"))
                    latency = parse_number(perf.get("latency_ms"))
                if model_size is not None:
                    accuracy_model_size_pairs.append((model_size, accuracy))
                if latency is not None:
                    accuracy_latency_pairs.append((latency, accuracy))

    field_coverage = {}
    for field_id, counts in field_counts.items():
        total = sum(counts.values())
        field_coverage[field_id] = {
            "total": total,
            "value": counts.get("value", 0),
            "nr": counts.get("nr", 0),
            "empty_list": counts.get("empty_list", 0),
            "empty_object": counts.get("empty_object", 0),
            "missing": counts.get("missing", 0),
        }

    numeric_summaries = {name: summarize_numeric(values) for name, values in numeric_metrics.items()}
    normalized_metrics = {}
    for name, values in numeric_metrics.items():
        normalized = normalize_percentage(values)
        normalized_metrics[name] = {
            "summary": summarize_numeric(normalized["normalized"]),
            "counts": normalized["counts"],
            "outliers": normalized["outliers"][:20],
        }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(args.input),
        "schema_file": str(args.schema),
        "total_papers": total_papers,
        "group_coverage": dict(group_coverage),
        "field_coverage": field_coverage,
        "frequencies": {
            "task_types": task_types.most_common(args.top_k),
            "crop_species": list_frequencies["crop_species"].most_common(args.top_k),
            "disease_names": list_frequencies["disease_names"].most_common(args.top_k),
            "augmentation_methods": list_frequencies["augmentation_methods"].most_common(args.top_k),
            "domain_shift_handling": list_frequencies["domain_shift_handling"].most_common(args.top_k),
            "model_compression": list_frequencies["model_compression"].most_common(args.top_k),
            "generative_augmentation": list_frequencies["generative_augmentation"].most_common(args.top_k),
            "data_centric_methods": list_frequencies["data_centric_methods"].most_common(args.top_k),
            "explainability_methods": list_frequencies["explainability_methods"].most_common(args.top_k),
            "datasets": dataset_names.most_common(args.top_k),
            "dataset_domains": dataset_domains.most_common(args.top_k),
            "architectures": architecture_names.most_common(args.top_k),
            "optimizers": optimizer_counts.most_common(args.top_k),
            "regularization": regularization_counts.most_common(args.top_k),
        },
        "numeric_summaries": numeric_summaries,
        "normalized_metrics": normalized_metrics,
        "dataset_samples": summarize_numeric(dataset_samples),
        "dataset_classes": summarize_numeric(dataset_classes),
        "learning_rates": summarize_numeric(learning_rates),
        "epochs": summarize_numeric(epochs),
        "batch_sizes": summarize_numeric(batch_sizes),
        "token_estimates": {k: summarize_numeric(v) for k, v in token_estimates.items()},
        "pretrained_counts": dict(pretrained_counts),
        "correlations": {},
    }

    def add_corr(name: str, pairs: list[tuple[float, float]]) -> None:
        if len(pairs) < 3:
            return
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        summary["correlations"][name] = {
            "n": len(pairs),
            "pearson": pearson_corr(xs, ys),
            "spearman": spearman_corr(xs, ys),
        }

    add_corr("dataset_samples_vs_accuracy", accuracy_samples_pairs)
    add_corr("model_size_mb_vs_accuracy", accuracy_model_size_pairs)
    add_corr("latency_ms_vs_accuracy", accuracy_latency_pairs)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = output_dir / "full_text_stats_charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "full_text_stats.json"
    md_path = output_dir / "full_text_stats.md"

    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = []
    lines.append("# Full-Text Extraction Summary")
    lines.append("")
    lines.append(f"Generated: {summary['generated_at']}")
    lines.append(f"Input: `{summary['input_file']}`")
    lines.append(f"Schema: `{summary['schema_file']}`")
    lines.append(f"Total papers: **{total_papers}**")
    lines.append("")

    lines.append("## Group Coverage")
    for group_id, count in sorted(group_coverage.items()):
        pct = (count / total_papers * 100) if total_papers else 0
        lines.append(f"- {group_id}: {count} ({pct:.1f}%)")
    lines.append("")

    lines.append("## Field Coverage (Reported vs NR/Empty)")
    lines.append("| Field | Reported | NR | Empty List | Empty Object | Missing |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for field_id, stats in sorted(field_coverage.items()):
        lines.append(
            f"| {field_id} | {stats['value']} | {stats['nr']} | "
            f"{stats['empty_list']} | {stats['empty_object']} | {stats['missing']} |"
        )
    lines.append("")

    def add_top(title: str, items: list[tuple[str, int]]) -> None:
        lines.append(f"## {title}")
        for name, count in items:
            lines.append(f"- {name}: {count}")
        lines.append("")

    add_top("Task Types", summary["frequencies"]["task_types"])
    add_top("Top Crop Species", summary["frequencies"]["crop_species"])
    add_top("Top Disease Names", summary["frequencies"]["disease_names"])
    add_top("Top Architectures", summary["frequencies"]["architectures"])
    add_top("Top Datasets", summary["frequencies"]["datasets"])
    add_top("Dataset Domains", summary["frequencies"]["dataset_domains"])

    lines.append("## Numeric Summaries (Raw Values)")
    for metric, stats in numeric_summaries.items():
        if not stats:
            continue
        lines.append(
            f"- {metric}: n={stats['count']}, mean={stats['mean']:.4f}, "
            f"median={stats['median']:.4f}, min={stats['min']:.4f}, "
            f"max={stats['max']:.4f}"
        )
        scale = stats.get("scale_hint", {})
        if scale:
            lines.append(
                f"  - scale hint: <=1={scale.get('lte_1', 0)}, "
                f">1={scale.get('gt_1', 0)} (1-100={scale.get('gt_1_le_100', 0)})"
            )
    lines.append("")

    lines.append("## Normalized Metrics (0-1 Scale)")
    for metric, stats in normalized_metrics.items():
        summary_stats = stats.get("summary")
        if not summary_stats:
            continue
        counts = stats.get("counts", {})
        lines.append(
            f"- {metric}: n={summary_stats['count']}, mean={summary_stats['mean']:.4f}, "
            f"median={summary_stats['median']:.4f}, min={summary_stats['min']:.4f}, "
            f"max={summary_stats['max']:.4f}"
        )
        lines.append(
            f"  - scale counts: <=1={counts.get('lte_1', 0)}, "
            f"1-100={counts.get('gt_1_le_100', 0)}, >100={counts.get('gt_100', 0)}"
        )
    lines.append("")

    lines.append("## Training Hyperparameters (Raw Values)")
    for label, stats in [
        ("learning_rate", summary["learning_rates"]),
        ("epochs", summary["epochs"]),
        ("batch_size", summary["batch_sizes"]),
    ]:
        if not stats:
            continue
        lines.append(
            f"- {label}: n={stats['count']}, mean={stats['mean']:.4f}, "
            f"median={stats['median']:.4f}, min={stats['min']:.4f}, "
            f"max={stats['max']:.4f}"
        )
    lines.append("")

    if summary["correlations"]:
        lines.append("## Correlations (Accuracy vs Other Factors)")
        for name, stats in summary["correlations"].items():
            lines.append(
                f"- {name}: n={stats['n']}, pearson={stats['pearson']:.3f}, "
                f"spearman={stats['spearman']:.3f}"
            )
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    # Charts
    save_bar_chart("Task Types", summary["frequencies"]["task_types"], charts_dir / "task_types.png")
    save_bar_chart("Top Crop Species", summary["frequencies"]["crop_species"], charts_dir / "crop_species.png")
    save_bar_chart("Top Disease Names", summary["frequencies"]["disease_names"], charts_dir / "disease_names.png")
    save_bar_chart("Top Architectures", summary["frequencies"]["architectures"], charts_dir / "architectures.png")
    save_bar_chart("Top Datasets", summary["frequencies"]["datasets"], charts_dir / "datasets.png")
    save_bar_chart("Optimizers", summary["frequencies"]["optimizers"], charts_dir / "optimizers.png")

    for metric, values in numeric_metrics.items():
        normalized = normalize_percentage(values)
        save_histogram(
            f"{metric} (normalized)",
            normalized["normalized"],
            charts_dir / f"{metric.replace('.', '_')}_normalized.png",
            bins=20,
            xlabel="value (0-1)",
        )

    save_histogram(
        "Dataset Samples (log10)",
        dataset_samples,
        charts_dir / "dataset_samples.png",
        bins=20,
        log_scale=True,
        xlabel="samples",
    )
    save_histogram(
        "Dataset Classes",
        dataset_classes,
        charts_dir / "dataset_classes.png",
        bins=20,
        xlabel="classes",
    )
    save_histogram(
        "Learning Rate (log10)",
        learning_rates,
        charts_dir / "learning_rate.png",
        bins=20,
        log_scale=True,
        xlabel="learning rate",
    )
    save_histogram(
        "Epochs",
        epochs,
        charts_dir / "epochs.png",
        bins=20,
        xlabel="epochs",
    )
    save_histogram(
        "Batch Size",
        batch_sizes,
        charts_dir / "batch_size.png",
        bins=15,
        xlabel="batch size",
    )
    for metric in ["latency_ms", "throughput_fps", "model_size_mb", "memory_usage_mb"]:
        values = numeric_metrics.get(f"inference_performance.{metric}", [])
        save_histogram(
            f"Inference {metric}",
            values,
            charts_dir / f"inference_{metric}.png",
            bins=15,
            log_scale=metric in {"latency_ms", "model_size_mb", "memory_usage_mb"},
            xlabel=metric,
        )

    if accuracy_samples_pairs:
        xs = [p[0] for p in accuracy_samples_pairs]
        ys = [p[1] for p in accuracy_samples_pairs]
        save_scatter(
            "Dataset Samples vs Accuracy",
            xs,
            ys,
            charts_dir / "corr_samples_accuracy.png",
            x_log=True,
            xlabel="samples (log10)",
            ylabel="accuracy (0-1)",
        )
    if accuracy_model_size_pairs:
        xs = [p[0] for p in accuracy_model_size_pairs]
        ys = [p[1] for p in accuracy_model_size_pairs]
        save_scatter(
            "Model Size vs Accuracy",
            xs,
            ys,
            charts_dir / "corr_model_size_accuracy.png",
            x_log=True,
            xlabel="model size (MB, log10)",
            ylabel="accuracy (0-1)",
        )
    if accuracy_latency_pairs:
        xs = [p[0] for p in accuracy_latency_pairs]
        ys = [p[1] for p in accuracy_latency_pairs]
        save_scatter(
            "Latency vs Accuracy",
            xs,
            ys,
            charts_dir / "corr_latency_accuracy.png",
            x_log=True,
            xlabel="latency (ms, log10)",
            ylabel="accuracy (0-1)",
        )

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote charts to {charts_dir}")


if __name__ == "__main__":
    main()
