"""Small UI helper functions to keep widget code compact."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from laser.core.tlb8800.models import NumericBinding, SelectBinding


class ClickStepDoubleSpinBox(QDoubleSpinBox):
    """Arrows/wheel step by ``click_step``; typed values can be any float."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setKeyboardTracking(False)
        self.setCorrectionMode(QAbstractSpinBox.CorrectionMode.CorrectToNearestValue)
        self._click_step = 1.0

    def set_click_step(self, step: float) -> None:
        self._click_step = float(step)

    def stepBy(self, steps: int) -> None:
        self.setValue(self.value() + steps * self._click_step)
        self.editingFinished.emit()

    def typed_value(self) -> float:
        """Value from the text box (what the user typed), not a stale cached spin value."""
        line = self.lineEdit()
        text = line.text().strip().replace(",", "") if line is not None else ""
        if text:
            try:
                raw = float(text)
            except ValueError:
                self.interpretText()
                raw = float(self.value())
        else:
            self.interpretText()
            raw = float(self.value())
        return min(max(raw, self.minimum()), self.maximum())


def make_group(title: str, *, grid: bool = False) -> tuple[QGroupBox, QVBoxLayout | QGridLayout]:
    box = QGroupBox(title)
    layout: QVBoxLayout | QGridLayout = QGridLayout() if grid else QVBoxLayout()
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)
    box.setLayout(layout)
    return box, layout


def set_field_expanding(widget: QWidget) -> None:
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def make_click_spin(
    *,
    decimals: int,
    click_step: float,
    maximum: float,
    minimum: float | None = None,
    value: float | None = None,
) -> ClickStepDoubleSpinBox:
    spin = ClickStepDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.set_click_step(click_step)
    spin.setMaximum(maximum)
    if minimum is not None:
        spin.setMinimum(minimum)
    if value is not None:
        spin.setValue(value)
    set_field_expanding(spin)
    return spin


def fill_combo(combo: QComboBox, options: dict[int, str]) -> None:
    combo.clear()
    for key, label in options.items():
        combo.addItem(label, key)


def apply_numeric_binding(
    spin: ClickStepDoubleSpinBox,
    binding: NumericBinding,
    *,
    decimals: int,
    click_step: float | None = None,
) -> None:
    spin.setEnabled(binding.enabled)
    spin.blockSignals(True)
    try:
        spin.setMinimum(float(binding.minimum) if binding.minimum is not None else -1e12)
        spin.setMaximum(float(binding.maximum) if binding.maximum is not None else 1e12)
        spin.setDecimals(decimals)
        spin.setSingleStep(10 ** (-decimals))
        spin.set_click_step(click_step if click_step is not None else float(binding.step))
        if binding.value is not None:
            spin.setValue(float(binding.value))
    finally:
        spin.blockSignals(False)


def apply_select_binding(combo: QComboBox, binding: SelectBinding) -> None:
    combo.blockSignals(True)
    try:
        combo.setEnabled(binding.enabled)
        if binding.value is None:
            combo.setCurrentIndex(-1)
            return
        target = int(binding.value)
        for idx in range(combo.count()):
            data = combo.itemData(idx)
            if data is not None and int(data) == target:
                combo.setCurrentIndex(idx)
                return
        combo.setCurrentIndex(-1)
    finally:
        combo.blockSignals(False)
