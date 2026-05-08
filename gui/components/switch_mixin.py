"""QCheckBox Switch-style appearance QSS."""
SWITCH_QSS = """
QCheckBox::indicator {
    width: 36px; height: 18px; border-radius: 9px;
    background-color: #D1D5DB; border: none;
}
QCheckBox::indicator:checked {
    background-color: #4F46E5;
}
QCheckBox::indicator:disabled {
    opacity: 0.4;
}
"""