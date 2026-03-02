# ---------------- SIZE BIN DEFINITIONS ---------------- #

BC_BINS = {
    "XS": (266.529, 315.221),
    "S": (299.743, 349.507),
    "M": (332.936, 383.814),
    "L": (366.114, 418.136),
}

FC_BINS = {
    "XS": (208.958, 255.442),
    "S": (229.545, 278.055),
    "M": (250.122, 300.678),
    "L": (270.691, 323.309),
}

AR_BINS = {
    1: (293, 306.6),
    2: (306.6, 320.2),
    3: (320.2, 333.8),
    4: (333.8, 347.4),
    5: (347.4, 361),
}

RS_BINS = {
    1: (226, 239),
    2: (239, 252),
    3: (252, 265),
    4: (265, 278),
    5: (278, 291),
}

WIDTH_ORDER = ["XS", "S", "M", "L"]


# ---------------- HELPER FUNCTIONS ---------------- #

def find_bins(value, bins):
    """Return all bins that the value falls into, including overlaps."""
    matches = []
    for label, (low, high) in bins.items():
        if low <= value <= high:
            matches.append(label)
    return matches


def choose_larger_bin(bin_list):
    """Return the largest width bin from a list of candidates."""
    return max(bin_list, key=lambda b: WIDTH_ORDER.index(b))


# ---------------- WIDTH SIZING LOGIC ---------------- #

def determine_width_size(bc, fc):
    bc_bins = find_bins(bc, BC_BINS)
    fc_bins = find_bins(fc, FC_BINS)

    warning = ""

    # Case 1: both measurements land in a single bin.
    if len(bc_bins) == 1 and len(fc_bins) == 1:
        bc_bin = bc_bins[0]
        fc_bin = fc_bins[0]

        if bc_bin == fc_bin:
            return bc_bin, warning

        larger = choose_larger_bin([bc_bin, fc_bin])
        warning = (
            f"BC suggests {bc_bin}, FC suggests {fc_bin}. "
            f"Selected larger size {larger} to ensure component compatibility."
        )
        return larger, warning

    # Case 2: prefer the single-bin measurement when the other overlaps.
    if len(bc_bins) == 1 and len(fc_bins) > 1:
        return bc_bins[0], "FC overlaps bins; matched to BC size."

    if len(fc_bins) == 1 and len(bc_bins) > 1:
        return fc_bins[0], "BC overlaps bins; matched to FC size."

    # Case 3: both overlap, so choose the larger compatible size.
    if len(bc_bins) > 1 and len(fc_bins) > 1:
        combined = list(set(bc_bins + fc_bins))
        larger = choose_larger_bin(combined)
        warning = (
            f"BC bins: {bc_bins}, FC bins: {fc_bins}. "
            f"Selected larger size {larger}. Prosthetist discretion advised."
        )
        return larger, warning

    return None, "No valid width bin found."


# ---------------- LENGTH SIZING ---------------- #

def determine_length(value, bins):
    matches = find_bins(value, bins)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    # Overlaps resolve upward to avoid undersizing.
    return max(matches)


# ---------------- MAIN API FUNCTION ---------------- #

def compute_prosthesis_size(bc, fc, ar, rs):
    width_size, width_warning = determine_width_size(bc, fc)
    ar_length = determine_length(ar, AR_BINS)
    rs_length = determine_length(rs, RS_BINS)

    return {
        "width": width_size,
        "humeral_length": ar_length,
        "radial_length": rs_length,
        "message": width_warning,
    }
