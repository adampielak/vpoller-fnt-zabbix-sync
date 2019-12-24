def flatten(l):
    return [item for sublist in l for item in sublist]


def normalize_none(attr):
    if attr is None:
        attr = ""
    return attr


def yes_no(arg, type=bool):
    arg_lower = arg.lower()
    if type == bool:
        if arg_lower == "y" or arg_lower == "yes":
            return True
        return False
    if type == int:
        if arg_lower == "y" or arg_lower == "yes":
            return 1
        return 0
