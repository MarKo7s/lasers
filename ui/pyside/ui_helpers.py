"""Small UI helper functions to keep widget code compact."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.tlb8800.models import NumericBinding, SelectBinding


def make_group(title: str, *, grid: bool = False) -> tuple[QGroupBox, QVBoxLayout | QGridLayout]:
    """Create a titled group box with a ready layout."""
    box = QGroupBox(title)
    layout: QVBoxLayout | QGridLayout = QGridLayout() if grid else QVBoxLayout()
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)
    box.setLayout(layout)
    return box, layout


def set_field_expanding(widget: QWidget) -> None:
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def apply_numeric_binding_double(
    spin: QDoubleSpinBox,
    binding: NumericBinding,
    *,
    decimals: int,
) -> None:
    spin.setEnabled(binding.enabled)
    if binding.minimum is not None:
        spin.setMinimum(float(binding.minimum))
    if binding.maximum is not None:
        spin.setMaximum(float(binding.maximum))
    spin.setDecimals(decimals)
    spin.setSingleStep(float(binding.step))
    if binding.value is not None:
        spin.setValue(float(binding.value))


def apply_numeric_binding_int(
    spin: QSpinBox,
    binding: NumericBinding,
) -> None:
    spin.setEnabled(binding.enabled)
    if binding.minimum is not None:
        spin.setMinimum(int(round(binding.minimum)))
    if binding.maximum is not None:
        spin.setMaximum(int(round(binding.maximum)))
    spin.setSingleStep(int(round(binding.step)))
    if binding.value is not None:
        spin.setValue(int(round(binding.value)))


def apply_select_binding(combo: QComboBox, binding: SelectBinding) -> None:
    combo.setEnabled(binding.enabled)
    if binding.value is None:
        combo.setCurrentIndex(-1)
        return

    target = int(binding.value)
    for idx in range(combo.count()):
        if combo.itemData(idx) == target:
            combo.setCurrentIndex(idx)
            return
    combo.setCurrentIndex(-1)
