# ---------------- SIZE BIN DEFINITIONS ---------------- #

# Revised width sizing method:
# - 5 bins (XS-S-M-L-XL) for BC/FC
# - lower-end trim updated to 3% and upper-end trim kept at 5%
# - representative values are at 0.75 within each bin (defined for reporting/future use)
BC_BINS = {
    "XS": (266.0, 294.6),
    "S": (294.6, 323.2),
    "M": (323.2, 351.8),
    "L": (351.8, 380.4),
    "XL": (380.4, 409.0),
}

BC_REP_VALUES = {
    "XS": 287.45,
    "S": 316.05,
    "M": 344.65,
    "L": 373.25,
    "XL": 401.85,
}

FC_BINS = {
    "XS": (216.0, 234.36),
    "S": (234.36, 252.72),
    "M": (252.72, 271.08),
    "L": (271.08, 289.44),
    "XL": (289.44, 307.8),
}

FC_REP_VALUES = {
    "XS": 229.77,
    "S": 248.13,
    "M": 266.49,
    "L": 284.85,
    "XL": 303.21,
}

#Input variability thresholds for borderline classification, set at half the bin width for each bin. 
#sigma_anth = 0.02 * Median bin value
BC_SIGMA_INPUT = {
    "XS": 7.307,
    "S": 7.755,
    "M": 8.218,
    "L": 8.694,
    "XL": 9.180,
}

#sigma-anth = 0.03 * Median bin value
FC_SIGMA_INPUT = {
    "XS": 8.102,
    "S": 8.567,
    "M": 9.041,
    "L": 9.524,
    "XL": 10.014,
}

BC_BOUNDARY_TOL = {label: sigma / 2 for label, sigma in BC_SIGMA_INPUT.items()}
FC_BOUNDARY_TOL = {label: sigma / 2 for label, sigma in FC_SIGMA_INPUT.items()}
AR_BOUNDARY_TOL = 1.6105
RS_BOUNDARY_TOL = 2.149

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

WIDTH_ORDER = ["XS", "S", "M", "L", "XL"]


# ---------------- HELPER FUNCTIONS ---------------- #

def value_in_bin(value, low, high, is_last_bin=False):
    """Use left-inclusive/right-exclusive bins, except the final bin which is fully inclusive."""
    if is_last_bin:
        return low <= value <= high
    return low <= value < high


def find_bins(value, bins):
    """Return bins matched by ordered, non-overlapping boundary membership."""
    bin_items = list(bins.items())
    last_index = len(bin_items) - 1
    matches = []
    for index, (label, (low, high)) in enumerate(bin_items):
        if value_in_bin(value, low, high, is_last_bin=index == last_index):
            matches.append(label)
    return matches


def choose_larger_bin(bin_list):
    """Return the largest width bin from a list of candidates."""
    return max(bin_list, key=lambda b: WIDTH_ORDER.index(b))


def classify_measurement(value, bins, tolerance_by_bin):
    """Classify a width measurement as clear, borderline, or out_of_range."""
    bin_items = list(bins.items())
    if not bin_items:
        return "out_of_range", None, None, None, None

    min_val = bin_items[0][1][0]
    max_val = bin_items[-1][1][1]
    if value < min_val or value > max_val:
        return "out_of_range", None, None, None, None

    matches = find_bins(value, bins)
    if not matches:
        return "out_of_range", None, None, None, None

    assigned_bin = matches[0]
    bin_lower, bin_upper = bins[assigned_bin]
    tolerance = tolerance_by_bin.get(assigned_bin)
    if tolerance is None:
        tolerance = 0.0

    dist_low = value - bin_lower
    dist_high = bin_upper - value

    if dist_low <= tolerance:
        return "borderline", assigned_bin, "lower", dist_low, tolerance
    if dist_high <= tolerance:
        return "borderline", assigned_bin, "upper", dist_high, tolerance
    return "clear", assigned_bin, None, None, tolerance


def get_adjacent_size(bin_label, boundary_side):
    """Return adjacent width size by boundary side, or None if unavailable."""
    if bin_label not in WIDTH_ORDER:
        return None

    index = WIDTH_ORDER.index(bin_label)
    if boundary_side == "lower":
        if index == 0:
            return None
        return WIDTH_ORDER[index - 1]
    if boundary_side == "upper":
        if index == len(WIDTH_ORDER) - 1:
            return None
        return WIDTH_ORDER[index + 1]
    return None


def get_adjacent_length_bin(bin_label, boundary_side, bins):
    """Return adjacent length bin by boundary side, or None if unavailable."""
    ordered_bins = list(bins.keys())
    if bin_label not in ordered_bins:
        return None

    index = ordered_bins.index(bin_label)
    if boundary_side == "lower":
        if index == 0:
            return None
        return ordered_bins[index - 1]
    if boundary_side == "upper":
        if index == len(ordered_bins) - 1:
            return None
        return ordered_bins[index + 1]
    return None


def format_borderline_message(
    measure_name,
    value,
    assigned_bin,
    boundary_side,
    distance_to_boundary,
    tolerance_used,
):
    """Format advisory text for borderline BC/FC measurements."""
    adjacent_size = get_adjacent_size(assigned_bin, boundary_side)
    value_text = f"{value:.1f}"
    distance_text = f"{distance_to_boundary:.1f}"
    _ = tolerance_used  # classification uses this threshold; no need to display the value.

    if boundary_side == "upper":
        message = (
            f"{measure_name} measurement {value_text} mm falls in size {assigned_bin} and lies "
            f"{distance_text} mm below the upper boundary of that bin, which is within the "
            f"variability threshold."
        )
        if adjacent_size:
            message += (
                f" If limb fluctuation or future volume increase is expected, consider sizing up to "
                f"{adjacent_size}."
            )
        message += (
            f" If no change is expected, the current bin {assigned_bin} may be retained. If further "
            f"limb shrinkage or atrophy is expected, retaining the current bin is likely preferable."
        )
        return message

    message = (
        f"{measure_name} measurement {value_text} mm falls in size {assigned_bin} and lies "
        f"{distance_text} mm above the lower boundary of that bin, which is within the "
        f"variability threshold."
    )
    if adjacent_size:
        message += (
            f" The measurement is close to the adjacent smaller size {adjacent_size} boundary."
        )
    message += (
        f" If no change is expected, the current bin {assigned_bin} may be retained. Any "
        f"consideration of downsizing should be guided by clinical judgement and expected limb "
        f"volume change."
    )
    return message


def format_borderline_summary(measure_name):
    """Format concise summary text for borderline BC/FC measurements."""
    return f"{measure_name} measurement lies within the variability threshold."


# ---------------- WIDTH SIZING LOGIC ---------------- #

def determine_width_size(bc, fc):
    (
        bc_status,
        bc_class_bin,
        bc_boundary,
        bc_distance,
        bc_tol,
    ) = classify_measurement(bc, BC_BINS, BC_BOUNDARY_TOL)
    (
        fc_status,
        fc_class_bin,
        fc_boundary,
        fc_distance,
        fc_tol,
    ) = classify_measurement(fc, FC_BINS, FC_BOUNDARY_TOL)

    if bc_status == "out_of_range" or fc_status == "out_of_range":
        return (
            None,
            "Width measurement outside the supported anthropometric range. Clinical review required.",
            "",
        )

    bc_bins = find_bins(bc, BC_BINS)
    fc_bins = find_bins(fc, FC_BINS)

    width_size = None
    compatibility_message = ""

    # Case 1: both measurements land in a single bin.
    if len(bc_bins) == 1 and len(fc_bins) == 1:
        bc_bin = bc_bins[0]
        fc_bin = fc_bins[0]

        if bc_bin == fc_bin:
            width_size = bc_bin
        else:
            larger = choose_larger_bin([bc_bin, fc_bin])
            compatibility_message = (
                f"BC suggests {bc_bin}, FC suggests {fc_bin}. "
                f"Selected larger size {larger} to ensure component compatibility."
            )
            width_size = larger

    # Case 2: prefer the single-bin measurement when the other spans multiple bins.
    elif len(bc_bins) == 1 and len(fc_bins) > 1:
        width_size = bc_bins[0]
        compatibility_message = "FC spans multiple bins; matched to BC size."

    elif len(fc_bins) == 1 and len(bc_bins) > 1:
        width_size = fc_bins[0]
        compatibility_message = "BC spans multiple bins; matched to FC size."

    # Case 3: both overlap, so choose the larger compatible size.
    elif len(bc_bins) > 1 and len(fc_bins) > 1:
        combined = list(set(bc_bins + fc_bins))
        larger = choose_larger_bin(combined)
        compatibility_message = (
            f"BC bins: {bc_bins}, FC bins: {fc_bins}. "
            f"Selected larger size {larger}. Prosthetist discretion advised."
        )
        width_size = larger

    if width_size is None:
        return None, "No valid width bin found.", ""

    advisory_summaries = []
    advisory_details = []
    if bc_status == "borderline" and bc_class_bin is not None:
        advisory_summaries.append(format_borderline_summary("BC"))
        advisory_details.append(
            format_borderline_message(
                "BC",
                bc,
                bc_class_bin,
                bc_boundary,
                bc_distance,
                bc_tol,
            )
        )
    if fc_status == "borderline" and fc_class_bin is not None:
        advisory_summaries.append(format_borderline_summary("FC"))
        advisory_details.append(
            format_borderline_message(
                "FC",
                fc,
                fc_class_bin,
                fc_boundary,
                fc_distance,
                fc_tol,
            )
        )

    summary_messages = []
    detail_messages = []
    if compatibility_message:
        summary_messages.append(compatibility_message)
        detail_messages.append(compatibility_message)
    if advisory_summaries:
        summary_messages.append("\n\n".join(advisory_summaries))
    if advisory_details:
        detail_messages.append("\n\n".join(advisory_details))

    summary_text = "\n\n".join(summary_messages)
    detail_text = "\n\n".join(detail_messages)
    if detail_text == summary_text:
        detail_text = ""

    return width_size, summary_text, detail_text


# ---------------- LENGTH SIZING ---------------- #

def determine_length(value, bins):
    matches = find_bins(value, bins)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    # Overlaps resolve upward to avoid undersizing.
    return max(matches)


def classify_length_measurement(value, bins, tolerance):
    """Classify a length measurement as clear, borderline, or out_of_range."""
    bin_items = list(bins.items())
    if not bin_items:
        return "out_of_range", None, None, None, tolerance

    min_val = bin_items[0][1][0]
    max_val = bin_items[-1][1][1]
    if value < min_val or value > max_val:
        return "out_of_range", None, None, None, tolerance

    assigned_bin = determine_length(value, bins)
    if assigned_bin is None:
        return "out_of_range", None, None, None, tolerance

    bin_lower, bin_upper = bins[assigned_bin]
    dist_low = value - bin_lower
    dist_high = bin_upper - value

    if dist_low <= tolerance:
        return "borderline", assigned_bin, "lower", dist_low, tolerance
    if dist_high <= tolerance:
        return "borderline", assigned_bin, "upper", dist_high, tolerance
    return "clear", assigned_bin, None, None, tolerance


def format_length_borderline_message(
    measure_name,
    value,
    assigned_bin,
    boundary_side,
    distance_to_boundary,
    tolerance_used,
    bins,
):
    """Format advisory text for borderline AR/RS length measurements."""
    adjacent_bin = get_adjacent_length_bin(assigned_bin, boundary_side, bins)
    value_text = f"{value:.1f}"
    distance_text = f"{distance_to_boundary:.1f}"
    _ = tolerance_used  # classification uses this threshold; no need to display the value.

    if boundary_side == "upper":
        message = (
            f"{measure_name} measurement {value_text} mm falls in length bin {assigned_bin} and lies "
            f"{distance_text} mm below the upper boundary of that bin, which is within the "
            f"observer-error threshold."
        )
        if adjacent_bin is not None:
            message += (
                f" Clinical judgement is advised if the adjacent larger size boundary "
                f"(bin {adjacent_bin}) is being considered."
            )
        return message

    message = (
        f"{measure_name} measurement {value_text} mm falls in length bin {assigned_bin} and lies "
        f"{distance_text} mm above the lower boundary of that bin, which is within the "
        f"observer-error threshold."
    )
    if adjacent_bin is not None:
        message += (
            f" Clinical judgement is advised if the adjacent smaller size boundary "
            f"(bin {adjacent_bin}) is being considered."
    )
    return message


def format_length_borderline_summary(measure_name):
    """Format concise summary text for borderline AR/RS measurements."""
    return f"{measure_name} measurement lies within the observer-error threshold."


def format_length_out_of_range_message(measure_name, value, bins):
    """Format advisory text for unsupported AR/RS measurements."""
    bin_items = list(bins.items())
    if not bin_items:
        return f"{measure_name} measurement {value:.1f} mm is outside the supported length range and requires clinical review."

    min_val = bin_items[0][1][0]
    max_val = bin_items[-1][1][1]
    return (
        f"{measure_name} measurement {value:.1f} mm is outside the supported length range "
        f"({min_val:.1f}-{max_val:.1f} mm) and requires clinical review."
    )


def determine_length_with_warning(measure_name, value, bins, tolerance):
    """Return the assigned length bin together with any advisory warning text."""
    (
        status,
        assigned_bin,
        boundary_side,
        distance_to_boundary,
        tolerance_used,
    ) = classify_length_measurement(value, bins, tolerance)

    if status == "out_of_range":
        return None, format_length_out_of_range_message(measure_name, value, bins), ""

    if status == "borderline" and assigned_bin is not None:
        return (
            assigned_bin,
            format_length_borderline_summary(measure_name),
            format_length_borderline_message(
                measure_name,
                value,
                assigned_bin,
                boundary_side,
                distance_to_boundary,
                tolerance_used,
                bins,
            ),
        )

    return assigned_bin, "", ""


# ---------------- MAIN API FUNCTION ---------------- #

def compute_prosthesis_size(bc, fc, ar, rs):
    width_size, width_warning, width_details = determine_width_size(bc, fc)
    ar_length, ar_warning, ar_details = determine_length_with_warning(
        "AR",
        ar,
        AR_BINS,
        AR_BOUNDARY_TOL,
    )
    rs_length, rs_warning, rs_details = determine_length_with_warning(
        "RS",
        rs,
        RS_BINS,
        RS_BOUNDARY_TOL,
    )

    messages = [message for message in [width_warning, ar_warning, rs_warning] if message]
    details = [detail for detail in [width_details, ar_details, rs_details] if detail]

    return {
        "width": width_size,
        "humeral_length": ar_length,
        "radial_length": rs_length,
        "message": "\n\n".join(messages),
        "details": "\n\n".join(details),
    }
