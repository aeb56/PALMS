import os
import re
import sys
from collections import defaultdict
from PyQt6.QtCore import QTimer, Qt, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import *
from Experiment import RWArgs, Experiment, Phase
from Plots import show_plots, generate_figures
from Environment import StimulusHistory

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib import pyplot

from itertools import chain

class CoolTable(QTableWidget):
    def __init__(self, rows: int, cols: int):
        super().__init__(rows, cols)
        self.setVerticalHeaders()
        self.setHorizontalHeaderItem(0, QTableWidgetItem('Phase 1'))
        self.itemChanged.connect(self.autoResize)
        self.freeze = False

    def getText(self, row: int, col: int) -> str:
        item = self.item(row, col)
        if item is None:
            return ""

        return item.text()

    def setVerticalHeaders(self):
        rows = self.rowCount()

        self.setVerticalHeaderItem(0, QTableWidgetItem('Control'))
        self.setVerticalHeaderItem(1, QTableWidgetItem('Test'))

        firstNum = 2 if rows <= 3 else 1
        for e in range(firstNum, rows):
            self.setVerticalHeaderItem(e, QTableWidgetItem(f'Test {e}'))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            for item in self.selectedItems():
                item.setText('')
        else:
            super().keyPressEvent(event)

    def addInsetTextColumn(self):
        currentColumnCount = self.columnCount()
        self.setColumnCount(currentColumnCount + 1)
        self.inset_text_column_index = currentColumnCount
        self.setHorizontalHeaderItem(
            self.inset_text_column_index,
            QTableWidgetItem("Inset Text"),
        )

    def removeInsetTextColumn(self):
        currentColumnCount = self.columnCount()
        if currentColumnCount > 1 and self.inset_text_column_index is not None:
            self.removeColumn(self.inset_text_column_index)
            self.inset_text_column_index = None

    def autoResize(self, item):
        if self.freeze:
            return

        col = item.column()
        row = item.row()

        colCount = self.columnCount()
        rowCount = self.rowCount()

        if item.text():
            if col == colCount - 1:
                self.addColumn()

            if row == rowCount - 1:
                self.addRow()
        else:
            if col == colCount - 2 and not any(self.getText(x, col) for x in range(colCount)):
                self.removeColumn()

            if row == rowCount - 2 and not any(self.getText(x, row) for x in range(rowCount)):
                self.removeRow()

    def addColumn(self):
        cols = self.columnCount()
        self.insertColumn(cols)
        self.setHorizontalHeaderItem(cols, QTableWidgetItem(f'Phase {cols + 1}'))

    def removeColumn(self):
        currentColumnCount = self.columnCount()
        self.setColumnCount(currentColumnCount - 1)

    def addRow(self):
        rows = self.rowCount()
        self.insertRow(rows)
        self.setVerticalHeaders()

    def removeRow(self):
        currentRowCount = self.rowCount()
        self.setRowCount(currentRowCount - 1)
        self.setVerticalHeaders()

    def loadFile(self, lines):
        self.freeze = True

        self.setRowCount(len(lines))

        maxCols = 0
        for row, group in enumerate(lines):
            name, *phase_strs = [x.strip() for x in group.split('|')]

            if len(phase_strs) > maxCols:
                maxCols = len(phase_strs)
                self.setColumnCount(maxCols)
                self.setHorizontalHeaderLabels([f'Phase {x}' for x in range(1, maxCols + 1)])

            self.setVerticalHeaderItem(row, QTableWidgetItem(name))
            for col, phase in enumerate(phase_strs):
                self.setItem(row, col, QTableWidgetItem(phase))

        self.freeze = False

class PavlovianApp(QDialog):
    def __init__(self, parent=None):
        super(PavlovianApp, self).__init__(parent)

        self.adaptive_types = ['rescorla_wagner', 'rescorla_wagner_linear', 'pearce_hall', 'pearce_kaye_hall', 'le_pelley']
        self.current_adaptive_type = None
        self.inset_text_column_index = None

        self.originalPalette = QApplication.palette()

        self.phase = 1
        self.numPhases = 0
        self.figures = []
        self.initUI()

        QTimer.singleShot(100, self.updateWidgets)

    def initUI(self):
        styleComboBox = QComboBox()
        styleComboBox.addItems(QStyleFactory.keys())

        styleLabel = QLabel("&Style:")
        styleLabel.setBuddy(styleComboBox)

        self.useStylePaletteCheckBox = QCheckBox("&Use style's standard palette")
        self.useStylePaletteCheckBox.setChecked(True)

        disableWidgetsCheckBox = QCheckBox("&Disable widgets")

        self.tableWidget = CoolTable(2, 1)
        self.tableWidget.setMaximumHeight(120)

        self.addActionsButtons()
        self.createParametersGroupBox()

        self.plotBox = QGroupBox('Plot')

        self.plotCanvas = FigureCanvasQTAgg()
        self.phaseBox = QGroupBox()

        self.phaseBoxLayout = QGridLayout()
        self.leftPhaseButton = QPushButton('<')
        self.leftPhaseButton.clicked.connect(self.prevPhase)

        self.phaseInfo = QLabel('')
        self.rightPhaseButton = QPushButton('>')
        self.rightPhaseButton.clicked.connect(self.nextPhase)

        self.phaseBoxLayout.addWidget(self.leftPhaseButton, 0, 0, 1, 1)
        self.phaseBoxLayout.addWidget(self.phaseInfo, 0, 1, 1, 4, Qt.AlignmentFlag.AlignCenter)
        self.phaseBoxLayout.addWidget(self.rightPhaseButton, 0, 6, 1, 1)
        self.phaseBox.setLayout(self.phaseBoxLayout)

        self.plotBoxLayout = QVBoxLayout()
        self.plotBoxLayout.addWidget(self.plotCanvas)
        self.plotBoxLayout.addWidget(self.phaseBox)
        self.plotBoxLayout.setStretch(0, 1)
        self.plotBoxLayout.setStretch(1, 0)
        self.plotBox.setLayout(self.plotBoxLayout)

        self.adaptiveTypeButtons = self.addAdaptiveTypeButtons()

        mainLayout = QGridLayout()
        mainLayout.addWidget(self.tableWidget, 0, 0, 1, 4)
        mainLayout.addWidget(self.adaptiveTypeButtons, 1, 0, 2, 1)
        mainLayout.addWidget(self.parametersGroupBox, 1, 1, 2, 1)
        mainLayout.addWidget(self.plotBox, 1, 2, 2, 1)
        mainLayout.addWidget(self.plotOptionsGroupBox, 1, 3, 1, 1)
        mainLayout.addWidget(self.fileOptionsGroupBox, 2, 3, 1, 1)
        mainLayout.setRowStretch(0, 1)
        mainLayout.setRowStretch(1, 0)
        mainLayout.setRowStretch(2, 1)
        mainLayout.setColumnStretch(0, 0)
        mainLayout.setColumnStretch(1, 0)
        mainLayout.setColumnStretch(2, 1)
        mainLayout.setColumnStretch(3, 0)
        self.setLayout(mainLayout)

        self.setWindowTitle("🐕🔔")
        self.restoreDefaultParameters()

        self.initialAdaptiveTypeButton.click()

        self.resize(1250, 600)

    def addAdaptiveTypeButtons(self):
        buttons = QGroupBox('Adaptive Type')
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        buttonGroup = QButtonGroup(self)
        buttonGroup.setExclusive(True)

        for i, adaptive_type in enumerate(self.adaptive_types):
            button = QPushButton(' '.join(x.capitalize() for x in re.findall(r'[a-z]+', adaptive_type)))
            button.adaptive_type = adaptive_type
            button.setCheckable(True)

            noMarginStyle = ""
            checkedStyle = "QPushButton:checked { background-color: lightblue; font-weight: bold; border: 2px solid #0057D8; }"
            button.setStyleSheet(noMarginStyle + checkedStyle)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

            buttonGroup.addButton(button, i)
            layout.addWidget(button)

            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if adaptive_type == 'le_pelley':
                button.setChecked(True)
                self.initialAdaptiveTypeButton = button

        buttonGroup.buttonClicked.connect(self.changeAdaptiveType)
        buttons.setLayout(layout)
        return buttons

    def openFileDialog(self):
        file, _ = QFileDialog.getOpenFileName(self, 'Open File', './Experiments')
        self.tableWidget.loadFile([x.strip() for x in open(file)])
        self.refreshExperiment()

    def addActionsButtons(self):
        self.plotOptionsGroupBox = QGroupBox("Plot Options")
        self.fileOptionsGroupBox = QGroupBox("File Options")

        self.fileButton = QPushButton('Load file')
        self.fileButton.clicked.connect(self.openFileDialog)

        self.saveButton = QPushButton("Save Experiment")
        self.saveButton.clicked.connect(self.saveExperiment)

        self.plotAlphaButton = QPushButton('Plot α')
        checkedStyle = "QPushButton:checked { background-color: lightblue; font-weight: bold; border: 2px solid #0057D8; }"
        self.plotAlphaButton.setStyleSheet(checkedStyle)
        self.plotAlphaButton.setFixedHeight(50)
        self.plotAlphaButton.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.plotAlphaButton.clicked.connect(self.togglePlotAlpha)
        self.plotAlphaButton.setCheckable(True)
        self.plot_alpha = False

        self.setDefaultParamsButton = QPushButton("Restore Default Parameters")
        self.setDefaultParamsButton.clicked.connect(self.restoreDefaultParameters)

        self.refreshButton = QPushButton("Refresh")
        self.refreshButton.clicked.connect(self.refreshExperiment)

        self.printButton = QPushButton("Plot")
        self.printButton.clicked.connect(self.plotExperiment)

        plotOptionsLayout = QVBoxLayout()
        plotOptionsLayout.addWidget(self.plotAlphaButton)
        plotOptionsLayout.addWidget(self.refreshButton)
        plotOptionsLayout.addWidget(self.printButton)
        self.plotOptionsGroupBox.setLayout(plotOptionsLayout)

        fileOptionsLayout = QVBoxLayout()
        fileOptionsLayout.addWidget(self.fileButton)
        fileOptionsLayout.addWidget(self.saveButton)
        fileOptionsLayout.addWidget(self.setDefaultParamsButton)
        fileOptionsLayout.addStretch()
        self.fileOptionsGroupBox.setLayout(fileOptionsLayout)

    def togglePlotAlpha(self):
        self.plot_alpha = not self.plot_alpha
        self.refreshExperiment()

    def saveExperiment(self):
        default_directory = os.path.join(os.getcwd(), 'Experiments')
        os.makedirs(default_directory, exist_ok=True)
        default_file_name = os.path.join(default_directory, "experiment.rw")

        fileName, _ = QFileDialog.getSaveFileName(self, "Save Experiment", default_file_name, "RW Files (*.rw);;All Files (*)")
        if not fileName:
            return

        if not fileName.endswith(".rw"):
            fileName += ".rw"

        rowCount = self.tableWidget.rowCount()
        columnCount = self.tableWidget.columnCount()
        while columnCount > 0 and not any(self.tableWidget.getText(row, columnCount - 1) for row in range(rowCount)):
            columnCount -= 1

        lines = []
        for row in range(rowCount):
            name = self.tableWidget.verticalHeaderItem(row).text()
            phase_strs = [self.tableWidget.getText(row, column) for column in range(columnCount)]
            if not any(phase_strs):
                continue

            lines.append(name + '|' + '|'.join(phase_strs))

        with open(fileName, 'w') as file:
            for line in lines:
                file.write(line + '\n')

    def changeAdaptiveType(self, button):
        self.current_adaptive_type = button.adaptive_type

        widgets_to_enable = {
            'rescorla_wagner': ['alpha', 'beta', 'lamda'],
            'rescorla_wagner_linear': ['alpha', 'beta', 'lamda'],
            'pearce_hall': ['alpha', 'lamda', 'salience'],
            'pearce_kaye_hall': ['alpha', 'betan', 'beta', 'gamma', 'lamda', 'lamda'],
            'le_pelley': ['alpha', 'betan', 'beta', 'lamda', 'thetaE', 'thetaI'],
        }

        for key in ['alpha', 'lamda', 'beta', 'betan', 'gamma', 'thetaE', 'thetaI', 'window_size', 'salience']:
            widget = getattr(self, f'{key}').box
            widget.setDisabled(True)

        for key in widgets_to_enable[self.current_adaptive_type]:
            widget = getattr(self, f'{key}').box
            widget.setDisabled(False)

        self.refreshExperiment()

    def createParametersGroupBox(self):
        self.parametersGroupBox = QGroupBox("Parameters")
        self.parametersGroupBox.setMaximumWidth(100)

        class DualLabel:
            def __init__(self, text, layout, parent, font = None):
                self.label = QLabel(text)
                self.box = QLineEdit()
                self.box.returnPressed.connect(parent.refreshExperiment)

                if font is not None:
                    self.label.setFont(QFont(font))

                layout.addRow(self.label, self.box)

        params = QFormLayout()
        self.alpha = DualLabel("α ", params, self, 'Monospace')
        self.alpha_mack = DualLabel("αᴹ", params, self, 'Monospace')
        self.alpha_hall = DualLabel("αᴴ", params, self, 'Monospace')
        self.lamda = DualLabel("λ ", params, self, 'Monospace')
        self.beta = DualLabel("β⁺", params, self, 'Monospace')
        self.betan = DualLabel("β⁻", params, self, 'Monospace')
        self.gamma = DualLabel("γ ", params, self, 'Monospace')
        self.thetaE = DualLabel("θᴱ", params, self, 'Monospace')
        self.thetaI = DualLabel("θᴵ", params, self, 'Monospace')
        self.salience = DualLabel("S ", params, self, 'Monospace')
        self.window_size = DualLabel("WS", params, self)
        self.num_trials = DualLabel("№", params, self)

        params.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.parametersGroupBox.setLayout(params)

    def restoreDefaultParameters(self):
        defaults = {
            'alpha': '0.1',
            'lamda': '1',
            'beta': '0.3',
            'betan': '0.2',
            'gamma': '0.5',
            'thetaE': '0.3',
            'thetaI': '0.1',
            'salience': '0.5',
            'window_size': '10',
            'num_trials': '100'
        }

        for key, value in defaults.items():
            widget = getattr(self, f'{key}').box
            widget.setText(value)

    @staticmethod
    def floatOrNone(text: str) -> None | float:
        if text == '':
            return None
        return float(text)

    def generateResults(self) -> tuple[dict[str, StimulusHistory], dict[str, list[Phase]], RWArgs]:
        args = RWArgs(
            adaptive_type = self.current_adaptive_type,

            alphas = defaultdict(lambda: float(self.alpha.box.text())),
            alpha = float(self.alpha.box.text()),
            alpha_mack = self.floatOrNone(self.alpha_mack.box.text()),
            alpha_hall = self.floatOrNone(self.alpha_hall.box.text()),

            beta = float(self.beta.box.text()),
            beta_neg = float(self.betan.box.text()),
            lamda = float(self.lamda.box.text()),
            gamma = float(self.gamma.box.text()),
            thetaE = float(self.thetaE.box.text()),
            thetaI = float(self.thetaI.box.text()),

            salience = float(self.salience.box.text()),
            saliences = defaultdict(lambda: float(self.salience.box.text())),

            window_size = int(self.window_size.box.text()),
            num_trials = int(self.num_trials.box.text()),

            plot_alpha = self.plot_alpha,

            xi_hall = 0.5,
        )

        rowCount = self.tableWidget.rowCount()
        columnCount = self.tableWidget.columnCount()
        while columnCount > 0 and not any(self.tableWidget.getText(row, columnCount - 1) for row in range(rowCount)):
            columnCount -= 1

        strengths = [StimulusHistory.emptydict() for _ in range(columnCount)]
        phases = dict()
        for row in range(rowCount):
            name = self.tableWidget.verticalHeaderItem(row).text()
            phase_strs = [self.tableWidget.getText(row, column) for column in range(columnCount)]
            if not any(phase_strs):
                continue

            experiment = Experiment(name, phase_strs)
            local_strengths = experiment.run_all_phases(args)

            strengths = [a | b for a, b in zip(strengths, local_strengths)]
            phases[name] = experiment.phases

        return strengths, phases, args

    def refreshExperiment(self):
        for fig in self.figures:
            pyplot.close(fig)

        strengths, phases, args = self.generateResults()
        if len(phases) == 0:
            return

        self.numPhases = max(len(v) for v in phases.values())
        self.phase = min(self.phase, self.numPhases)

        self.figures = generate_figures(
            strengths,
            plot_alpha = args.plot_alpha,
            dpi = 175,
            ticker_threshold = 5,
        )
        for f in self.figures:
            f.set_canvas(self.plotCanvas)
        
        self.refreshFigure()

    def refreshFigure(self):
        current_figure = self.figures[self.phase - 1]
        current_figure.tight_layout()
        self.plotCanvas.figure = current_figure

        self.tableWidget.setRangeSelected(
            QTableWidgetSelectionRange(0, 0, self.tableWidget.rowCount() - 1, self.tableWidget.columnCount() - 1),
            False,
        )

        self.tableWidget.setRangeSelected(
            QTableWidgetSelectionRange(0, self.phase - 1, self.tableWidget.rowCount() - 1, self.phase - 1),
            True,
        )

        canvas_width = self.plotCanvas.width() * len(current_figure.get_axes()) // max(1, len(self.plotCanvas.figure.get_axes()))
        self.resize(
            self.width() - self.plotCanvas.width() + canvas_width,
            self.height(),
        )

        self.plotCanvas.resize(self.plotCanvas.width() - 1, self.plotCanvas.height() - 1)
        self.plotCanvas.resize(self.plotCanvas.width() + 1, self.plotCanvas.height() + 1)

        self.plotCanvas.mpl_connect('pick_event', self.pickLine)
        self.plotCanvas.draw()

        self.phaseInfo.setText(f'Phase {self.phase}/{self.numPhases}')

    def pickLine(self, event):
        line = event.artist
        label = line.get_label()

        for ax in line.figure.get_axes():
            for line in ax.get_lines():
                if line.get_label() == label:
                    line.set_alpha(.5 - line.get_alpha())

            for line in ax.get_legend().get_lines():
                if line.get_label() == label:
                    line.set_alpha(.75 - line.get_alpha())

        line.figure.canvas.draw_idle()

    def plotExperiment(self):
        strengths, phases, args = self.generateResults()
        if len(phases) == 0:
            return

        show_plots(
            strengths,
            phases = phases,
            plot_alpha = args.plot_alpha,
        )

        return strengths

    def updateWidgets(self):
        self.tableWidget.update()
        self.tableWidget.repaint()
        self.update()
        self.repaint()

    def prevPhase(self):
        if self.phase == 1:
            return

        self.phase -= 1
        self.refreshFigure()
    
    def nextPhase(self):
        if self.phase >= self.numPhases:
            return

        self.phase += 1 
        self.refreshFigure()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gallery = PavlovianApp()
    gallery.show()
    sys.exit(app.exec())
