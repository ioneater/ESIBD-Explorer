import sys

from asteval import Interpreter
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QGridLayout, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget

aeval = Interpreter()


class Calculator(QWidget):
    """Minimal calculator example in PyQt6."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle('PyQt6 Calculator')
        self.setGeometry(100, 100, 200, 100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        """Initialize UI components."""
        layout = QVBoxLayout()

        # Display for input/output
        self.display = QLineEdit()
        self.display.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.display.setStyleSheet('font-size: 24px')
        self.display.returnPressed.connect(self.evaluate)
        layout.addWidget(self.display)

        # Grid layout for buttons
        grid = QGridLayout()
        buttons = [
            ('7', '8', '9', '/'),
            ('4', '5', '6', '*'),
            ('1', '2', '3', '-'),
            ('0', 'C', '=', '+'),
        ]

        for row_idx, row in enumerate(buttons):
            for col_idx, label in enumerate(row):
                button = QPushButton(label)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                button.setMinimumSize(20, 20)
                button.setStyleSheet('font-size: 18px')
                button.clicked.connect(lambda checked, text=label: self.onButtonClick(text))  # noqa: ARG005
                grid.addWidget(button, row_idx, col_idx)

        layout.addLayout(grid)
        self.setLayout(layout)

    def onButtonClick(self, label) -> None:
        """Handle button clicks.

        :param label: Label representing function of the button.
        :type label: str
        """
        if label == '=':
            self.evaluate()
        elif label == 'C':
            self.display.clear()
        else:
            self.display.setText(self.display.text() + label)

    def evaluate(self) -> None:
        """Evaluate the equation."""
        try:
            result = aeval(self.display.text())
            self.display.setText(str(result))
        except Exception:  # noqa: BLE001
            self.display.setText('Error')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = Calculator()
    window.show()
    sys.exit(app.exec())
