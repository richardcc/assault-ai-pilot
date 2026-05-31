from collections import defaultdict


def build_strategy_option_map(results):
    """
    Mapping L3 → L2:
    For each formation (strategy), which options are used
    """

    mapping = defaultdict(lambda: defaultdict(int))

    for r in results:

        strat_map = r.get("strategy_option_map", {})

        for strategy, options in strat_map.items():
            for opt, count in options.items():
                mapping[strategy][opt] += count

    return mapping


def normalize_strategy_option_map(mapping):
    """
    Convert counts into percentages
    """

    normalized = {}

    for strat, opts in mapping.items():

        total = sum(opts.values()) or 1

        normalized[strat] = {
            opt: (count, count / total)
            for opt, count in opts.items()
        }

    return normalized