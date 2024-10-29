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

from argparse import ArgumentParser

import ipdb

class CoolTable(QWidget):
    def __init__(self, rows: int, cols: int, parent: None | QWidget = None):
        super().__init__(parent = parent)

        self.table = QTableWidget(rows, cols)
        self.table.setHorizontalHeaderItem(0, QTableWidgetItem('Phase 1'))
        self.table.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.rightPlus = QPushButton('+')
        self.rightPlus.clicked.connect(self.addColumn)

        self.bottomPlus = QPushButton('+')
        self.bottomPlus.clicked.connect(self.addRow)

        self.cButton = QPushButton('C')
        self.cButton.clicked.connect(self.removeEmptyCells)

        self.rightPlus.setFixedWidth(20)
        self.bottomPlus.setFixedHeight(20)
        self.cButton.setFixedSize(20, 20)

        self.layout = QGridLayout(parent = self)
        self.layout.addWidget(self.table, 0, 0, Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.rightPlus, 0, 1, Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.bottomPlus, 1, 0, Qt.AlignmentFlag.AlignLeft)
        self.layout.addWidget(self.cButton, 1, 1, Qt.AlignmentFlag.AlignLeft)
        self.layout.setColumnStretch(1, 1)
        self.layout.setSpacing(0)

        self.updateSizes()
        self.table.setHorizontalHeaderItem(0, QTableWidgetItem('Phase 1'))

    def getText(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        if item is None:
            return ""

        return item.text()

    def setVerticalHeaders(self):
        rows = self.rowCount()

        self.table.setVerticalHeaderItem(0, QTableWidgetItem('Control'))
        self.table.setVerticalHeaderItem(1, QTableWidgetItem('Test'))

        firstNum = 2 if rows <= 3 else 1
        for e in range(firstNum, rows):
            self.table.setVerticalHeaderItem(e, QTableWidgetItem(f'Test {e}'))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            for item in self.table.selectedItems():
                item.setText('')

    def updateSizes(self):
        self.setVerticalHeaders()

        w, h = self.table.width(), self.table.height()
        self.table.setFixedSize(90 * (1 + self.columnCount()), 30 * (1 + self.rowCount()))

        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.bottomPlus.setFixedWidth(self.table.width())
        self.rightPlus.setFixedHeight(self.table.height())

    def addColumn(self):
        cols = self.columnCount()
        self.table.insertColumn(cols)
        self.table.setHorizontalHeaderItem(cols, QTableWidgetItem(f'Phase {cols + 1}'))
        self.updateSizes()

    def removeColumn(self):
        currentColumnCount = self.columnCount()
        self.table.setColumnCount(currentColumnCount - 1)
        self.updateSizes()

    def addRow(self):
        rows = self.rowCount()
        self.table.insertRow(rows)
        self.updateSizes()

    def removeRow(self):
        currentRowCount = self.rowCount()
        self.table.setRowCount(currentRowCount - 1)
        self.updateSizes()

    def removeEmptyCells(self):
        pass

    def rowCount(self):
        return self.table.rowCount()

    def columnCount(self):
        return self.table.columnCount()

    def loadFile(self, lines):
        self.table.setRowCount(len(lines))

        maxCols = 0
        for row, group in enumerate(lines):
            name, *phase_strs = [x.strip() for x in group.split('|')]

            if len(phase_strs) > maxCols:
                maxCols = len(phase_strs)
                self.table.setColumnCount(maxCols)
                self.table.setHorizontalHeaderLabels([f'Phase {x}' for x in range(1, maxCols + 1)])

            self.table.setVerticalHeaderItem(row, QTableWidgetItem(name))
            for col, phase in enumerate(phase_strs):
                self.table.setItem(row, col, QTableWidgetItem(phase))

        self.updateSizes()

class PavlovianApp(QDialog):
    def __init__(self, dpi = 200, parent=None):
        super(PavlovianApp, self).__init__(parent)

        self.adaptive_types = ['rescorla_wagner', 'rescorla_wagner_linear', 'pearce_hall', 'pearce_kaye_hall', 'le_pelley', 'le_pelley_hybrid']
        self.current_adaptive_type = None
        self.inset_text_column_index = None

        self.originalPalette = QApplication.palette()

        self.phase = 1
        self.numPhases = 0
        self.figures = []
        self.dpi = dpi
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

        self.tableWidget = CoolTable(2, 1, parent = self)
        self.tableWidget.table.setMaximumHeight(120)

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
        
        self.expand_canvas = False

        self.plotAlphaButton = QPushButton('Plot α')
        checkedStyle = "QPushButton:checked { background-color: lightblue; font-weight: bold; border: 2px solid #0057D8; }"
        self.plotAlphaButton.setStyleSheet(checkedStyle)
        self.plotAlphaButton.setFixedHeight(50)
        self.plotAlphaButton.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.plotAlphaButton.clicked.connect(self.togglePlotAlpha)
        self.plotAlphaButton.setCheckable(True)
        self.plot_alpha = False
        self.plot_macknhall = False

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
        if self.plot_alpha or self.plot_macknhall:
            self.plot_alpha = False
            self.plot_macknhall = False
            self.resize(self.width() - self.plotCanvas.width() // 2, self.height())
        else:
            if self.current_adaptive_type != 'le_pelley_hybrid':
                self.plot_alpha = True
            else:
                self.plot_macknhall = True

            self.resize(self.width() + self.plotCanvas.width(), self.height())

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
            name = self.tableWidget.table.verticalHeaderItem(row).text()
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
            'le_pelley_hybrid': ['alpha', 'alpha_mack', 'alpha_hall', 'betan', 'beta', 'lamda', 'thetaE', 'thetaI'],
        }

        for key in ['alpha', 'alpha_mack', 'alpha_hall', 'lamda', 'beta', 'betan', 'gamma', 'thetaE', 'thetaI', 'window_size', 'salience']:
            widget = getattr(self, f'{key}').box
            widget.setDisabled(True)

        for key in widgets_to_enable[self.current_adaptive_type]:
            widget = getattr(self, f'{key}').box
            widget.setDisabled(False)

        if self.plot_alpha and self.current_adaptive_type == 'le_pelley_hybrid':
            self.plot_alpha = False
            self.plot_macknhall = True
        elif self.plot_macknhall and self.current_adaptive_type != 'le_pelley_hybrid':
            self.plot_alpha = True
            self.plot_macknhall = False

        if self.current_adaptive_type == 'le_pelley_hybrid':
            self.alpha.box.setText('0.9')

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
    def floatOr(text: str, default: None | float = None) -> None | float:
        if text == '':
            return default

        return float(text)

    def generateResults(self) -> tuple[dict[str, StimulusHistory], dict[str, list[Phase]], RWArgs]:
        args = RWArgs(
            adaptive_type = self.current_adaptive_type,

            alphas = defaultdict(lambda: self.floatOr(self.alpha.box.text(), 0)),
            alpha = self.floatOr(self.alpha.box.text(), 0),
            alpha_mack = self.floatOr(self.alpha_mack.box.text()),
            alpha_hall = self.floatOr(self.alpha_hall.box.text()),

            beta = self.floatOr(self.beta.box.text(), 0),
            beta_neg = self.floatOr(self.betan.box.text(), 0),
            lamda = self.floatOr(self.lamda.box.text(), 0),
            gamma = self.floatOr(self.gamma.box.text(), 0),
            thetaE = self.floatOr(self.thetaE.box.text(), 0),
            thetaI = self.floatOr(self.thetaI.box.text(), 0),

            salience = self.floatOr(self.salience.box.text(), 0),
            saliences = defaultdict(lambda: self.floatOr(self.salience.box.text(), 0)),

            window_size = int(self.window_size.box.text()),
            num_trials = int(self.num_trials.box.text()),

            plot_alpha = self.plot_alpha,
            plot_macknhall = self.plot_macknhall,

            xi_hall = 0.5,
        )

        rowCount = self.tableWidget.rowCount()
        columnCount = self.tableWidget.columnCount()
        while columnCount > 0 and not any(self.tableWidget.getText(row, columnCount - 1) for row in range(rowCount)):
            columnCount -= 1

        strengths = [StimulusHistory.emptydict() for _ in range(columnCount)]
        phases = dict()
        for row in range(rowCount):
            name = self.tableWidget.table.verticalHeaderItem(row).text()
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
            plot_macknhall = args.plot_macknhall,
            dpi = self.dpi,
            ticker_threshold = 5,
        )
        for f in self.figures:
            f.set_canvas(self.plotCanvas)

        self.refreshFigure()

    def refreshFigure(self):
        current_figure = self.figures[self.phase - 1]
        self.plotCanvas.figure = current_figure

        self.plotCanvas.resize(self.plotCanvas.width() + 1, self.plotCanvas.height() + 1)
        self.plotCanvas.resize(self.plotCanvas.width() - 1, self.plotCanvas.height() - 1)

        self.plotCanvas.mpl_connect('pick_event', self.pickLine)

        w, h = current_figure.get_size_inches()
        self.plotCanvas.draw()

        self.tableWidget.setRangeSelected(
            QTableWidgetSelectionRange(0, 0, self.tableWidget.rowCount() - 1, self.tableWidget.columnCount() - 1),
            False,
        )

        self.tableWidget.setRangeSelected(
            QTableWidgetSelectionRange(0, self.phase - 1, self.tableWidget.rowCount() - 1, self.phase - 1),
            True,
        )

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
            plot_macknhall = args.plot_macknhall,
            dpi = self.dpi,
        )

        return strengths

    def updateWidgets(self):
        self.tableWidget.update()
        self.tableWidget.repaint()
        self.tableWidget.updateSizes()
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

def parse_args():
    args = ArgumentParser('Display a GUI for simulating models.')
    args.add_argument('--dpi', type = int, default = 200, help = 'DPI for shown and outputted figures.')
    return args.parse_args()

if __name__ == '__main__':
    args = parse_args()
    app = QApplication(sys.argv)
    gallery = PavlovianApp(dpi = args.dpi)
    gallery.show()
    sys.exit(app.exec())
