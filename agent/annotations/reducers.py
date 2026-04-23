

def update_if_not_none[T](old: T, new: T) -> T:
    """Update the old value with the new value if the new value is not None. Otherwise, return the old value."""
    return new if new is not None else old

def update_if_not_true(old: bool, new: bool) -> bool:
    """Update the old value with the new value if the new value is not True. Otherwise, return the old value."""
    return new if new else old

__all__ = [
    update_if_not_none,
    update_if_not_true
]