import sys, requests
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QVBoxLayout,
    QWidget,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QComboBox,
    QLabel,
    QMenuBar,
    QAction,
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QDialog,
    QTextBrowser,
    QSpacerItem,
    QSizePolicy,
    QGraphicsOpacityEffect,
)
from PyQt5.QtCore import (
    Qt,
    QUrl,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QVariantAnimation,
    QEvent,
)
from PyQt5.QtGui import QDesktopServices, QFont, QColor, QPalette, QLinearGradient
from bs4 import BeautifulSoup
import warnings, re, os, json, csv, datetime, subprocess, platform
from io import StringIO

warnings.filterwarnings(
    "ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning
)
DATA_FILE_PATH = "extremist_materials_data.json"
CSV_URL = "https://minjust.gov.ru/uploaded/files/exportfsm.csv"
RSS_URL = "https://minjust.gov.ru/ru/subscription/rss/extremist_materials/"
ENCODINGS_TO_TRY = ["utf-8", "windows-1251", "cp1251", "latin-1", "cp866"]


class MaterialDetailDialog(QDialog):
    def __init__(self, parent, material_data):
        super().__init__(parent)
        self.setWindowTitle(
            f"Подробная информация о материале № {material_data.get('id','N/A')}"
        )
        self.setGeometry(parent.x() + 50, parent.y() + 50, 800, 600)
        self.setMinimumSize(1000, 600)
        self.setModal(True)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.material_data = material_data
        self.setStyleSheet(parent.get_dark_theme_stylesheet())
        self.setFocus()
        self.init_ui()
        self.display_material_details()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.detail_text_browser = QTextBrowser()
        self.detail_text_browser.setStyleSheet(
            "background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #505050; padding: 15px; border-radius: 5px;"
        )
        self.detail_text_browser.setOpenExternalLinks(True)
        layout.addWidget(self.detail_text_browser)
        disclaimer_label = QLabel(
            "<i style='color: #d17a3a;'>Если что-то пропарсилось неправильно - не моя вина, а вина тех, кто заполняет не стандартизированно и с неправильным синтаксисом/неграмотно</i>"
        )
        disclaimer_label.setWordWrap(True)
        disclaimer_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(disclaimer_label)
        close_button = QPushButton("Закрыть")
        close_button.setStyleSheet(
            "\n            QPushButton { \n                background-color: #d17a3a; \n                color: #ffffff; \n                border: none; \n                border-radius: 5px; \n                padding: 10px 15px; \n                font-weight: bold; \n            }\n            QPushButton:hover { \n                background-color: #e08b3a; \n            }\n        "
        )
        close_button.clicked.connect(self.force_close)
        layout.addWidget(close_button, alignment=Qt.AlignCenter)

    def force_close(self):
        self.done(QDialog.Accepted)

    def display_material_details(self):
        html_content = []
        html_content.append(
            "<h2 style='color: #d17a3a; text-align: center;'>Подробности о материале</h2>"
        )
        fields_order = [
            ("id", "№"),
            ("material_title", "Название материала"),
            ("author_or_publisher", "Автор/Издатель"),
            ("original_description", "Полное описание"),
            ("category", "Категория"),
            ("court_name", "Суд"),
            ("decision_date", "Дата решения"),
            ("entry_date", "Дата включения в список"),
            ("links", "Ссылки"),
        ]
        for (key, display_name) in fields_order:
            value = self.material_data.get(key, "Не указано")
            if key == "original_description":
                description_html = value
                url_pattern = (
                    '(?<!href=")(?P<url>(?:https?|ftp|sftp)://[^\\s/$.?#].[^\\s]*)'
                )
                description_html = re.sub(
                    url_pattern,
                    '<a href="\\g<url>" style="color: #e08b47;">\\g<url></a>',
                    description_html,
                )
                html_content.append(
                    f"<p><strong><span style='color: #a0a0a0;'>{display_name}:</span></strong> {description_html}</p>"
                )
            elif key == "links":
                if isinstance(value, list) and value:
                    link_html = "<ul style='margin-left: 15px;'>"
                    for link in value:
                        if link:
                            link_html += f"<li><a href='{link}' style='color: #e08b47;'>{link}</a></li>"
                    link_html += "</ul>"
                    html_content.append(
                        f"<p><strong><span style='color: #a0a0a0;'>{display_name}:</span></strong></p>{link_html}"
                    )
                else:
                    html_content.append(
                        f"<p><strong><span style='color: #a0a0a0;'>{display_name}:</span></strong> Не указано</p>"
                    )
            else:
                html_content.append(
                    f"<p><strong><span style='color: #a0a0a0;'>{display_name}:</span></strong> {value}</p>"
                )
        self.detail_text_browser.setHtml("\n".join(html_content))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape or event.key() == Qt.Key_Return:
            self.force_close()
        else:
            super().keyPressEvent(event)


class ExtrimistMaterialsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Федеральный список экстремистских материалов")
        self.setGeometry(100, 100, 800, 600)
        self.setMinimumSize(950, 600)
        self.data = []
        self.filtered_data = []
        self.index = {}
        self.categories = ["Все категории"]
        self.current_sort_column = -1
        self.current_sort_order = Qt.AscendingOrder
        self.rainbow_timer = QTimer(self)
        self.current_rainbow_color_index = 0
        self.rainbow_colors = self.generate_rainbow_colors()
        self.search_button_opacity_effect = QGraphicsOpacityEffect(self)
        self.status_label_opacity_effect = QGraphicsOpacityEffect(self)
        self.pulsating_animation = QPropertyAnimation(
            self.search_button_opacity_effect, b"opacity"
        )
        self.status_alpha_animation = QPropertyAnimation(
            self.status_label_opacity_effect, b"opacity"
        )
        self.status_message_label = QLabel()
        self.status_message_label.setAlignment(Qt.AlignCenter)
        self.status_message_label.setFont(QFont("Arial", 18, QFont.Bold))
        self.status_message_label.hide()
        self.color_animation = QVariantAnimation(self)
        self.color_animation.setStartValue(QColor(Qt.red))
        self.color_animation.setEndValue(QColor(Qt.blue))
        self.color_animation.setDuration(1000)
        self.color_animation.setEasingCurve(QEasingCurve.InOutSine)
        self.color_animation.setLoopCount(-1)
        self.color_animation.valueChanged.connect(self._update_status_label_color)
        self.status_message_container = QWidget()
        self.apply_global_font()
        self.setStyleSheet(self.get_dark_theme_stylesheet())
        self.create_menu()
        self.create_widgets()
        if not self.load_saved_data():
            self.load_data_from_web()
        self.setup_search_button_animation()
        self.setup_status_message_animation()

    def apply_global_font(self):
        font = QFont("Ubuntu", 10)
        QApplication.setFont(font)

    def get_dark_theme_stylesheet(self):
        return "\n        QMainWindow { background-color: #2b2b2b; color: #e0e0e0; }\n        QMenuBar { background-color: #3c3c3c; color: #e0e0e0; border-bottom: 1px solid #505050; }\n        QMenuBar::item { background-color: transparent; padding: 5px 10px; }\n        QMenuBar::item:selected { background-color: #555555; }\n        QMenu { background-color: #3c3c3c; border: 1px solid #505050; color: #e0e0e0; }\n        QMenu::item:selected { background-color: #555555; }\n        QLineEdit { background-color: #3c3c3c; border: 1px solid #505050; border-radius: 5px; padding: 12px; color: #e0e0e0; selection-background-color: #d17a3a; text-align: center; font-size: 20pt; }\n        QPushButton { background-color: #d17a3a; color: #ffffff; border: none; border-radius: 5px; padding: 12px 20px; font-weight: bold; font-size: 12pt; }\n        QPushButton:hover { background-color: #e08b47; }\n        QPushButton:pressed { background-color: #c06929; }\n        QTableWidget { background-color: #2b2b2b; alternate-background-color: #353535; color: #e0e0e0; border: 1px solid #505050; gridline-color: #505050; selection-background-color: #4a4a4a; selection-color: #e0e0e0; font-size: 10pt; }\n        QHeaderView::section { background-color: #3c3c3c; color: #e0e0e0; padding: 5px; border: 1px solid #505050; font-weight: bold; font-size: 10pt; }\n        QComboBox { background-color: #3c3c3c; border: 1px solid #505050; border-radius: 5px; padding: 8px; color: #d17a3a; selection-background-color: #d17a3a; selection-color: #ffffff; font-size: 11pt; }\n        QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 25px; border-left-width: 1px; border-left-color: #505050; border-left-style: solid; border-top-right-radius: 3px; border-bottom-right-radius: 3px; }\n        QComboBox QAbstractItemView { background-color: #3c3c3c; border: 1px solid #505050; selection-background-color: #d17a3a; color: #e0e0e0; font-size: 10pt; }\n        QLabel { color: #e0e0e0; font-size: 10pt; }\n        QToolTip { background-color: #4a4a4a; color: #e0e0e0; border: 1px solid #505050; padding: 5px; border-radius: 3px; font-size: 10pt; }\n        QDialog { background-color: #2b2b2b; color: #e0e0e0; }\n        QTextBrowser { background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #505050; padding: 10px; }\n        "

    def create_menu(self):
        menubar = self.menuBar()
        menubar.setCornerWidget(QWidget(), Qt.TopRightCorner)
        help_button_widget = QWidget()
        help_layout = QHBoxLayout(help_button_widget)
        help_layout.setContentsMargins(0, 0, 0, 0)
        help_layout.addStretch()
        howto_wtf_action = QAction("О программе и помощь", self)
        howto_wtf_action.triggered.connect(self.show_howto_wtf_dialog)
        help_menu_button = QPushButton("О программе и помощь")
        help_menu_button.clicked.connect(self.show_howto_wtf_dialog)
        help_menu_button.setStyleSheet(
            "\n            QPushButton { \n                background-color: transparent; \n                border: none; \n                padding: 5px 10px; \n                font-weight: normal; \n                font-size: 11pt; \n                color: #d17a3a;\n            }\n            QPushButton:hover { \n                background-color: #3c3c3c; \n            }\n            QPushButton:pressed { \n                background-color: #2b2b2b; \n            }\n        "
        )
        help_layout.addWidget(help_menu_button)
        help_layout.addStretch()
        menubar.setCornerWidget(help_button_widget, Qt.TopLeftCorner)

    def create_widgets(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Введите запрос для поиска...")
        self.search_input.setAlignment(Qt.AlignCenter)
        self.search_input.returnPressed.connect(self.perform_search)
        main_layout.addWidget(self.search_input)
        controls_layout = QHBoxLayout()
        controls_layout.addStretch()
        search_criteria_label = QLabel("Искать по:")
        search_criteria_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        controls_layout.addWidget(search_criteria_label)
        self.search_criteria = QComboBox()
        self.search_criteria.addItems(
            [
                "Все поля",
                "Номер",
                "Название материала",
                "Автор",
                "Описание",
                "Дата включения",
                "Суд",
                "Категория",
            ]
        )
        controls_layout.addWidget(self.search_criteria)
        controls_layout.addSpacerItem(
            QSpacerItem(20, 0, QSizePolicy.Fixed, QSizePolicy.Minimum)
        )
        category_label = QLabel("Категория:")
        category_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        controls_layout.addWidget(category_label)
        self.category_filter = QComboBox()
        self.category_filter.addItems(self.categories)
        self.category_filter.currentIndexChanged.connect(self.perform_search)
        controls_layout.addWidget(self.category_filter)
        controls_layout.addStretch()
        main_layout.addLayout(controls_layout)
        buttons_layout = QHBoxLayout()
        file_load_buttons_vlayout = QVBoxLayout()
        file_load_buttons_vlayout.setContentsMargins(0, 0, 0, 0)
        file_load_buttons_vlayout.setSpacing(5)
        self.load_file_button = QPushButton("Загрузить из файла (CSV/XML)")
        self.load_file_button.clicked.connect(self.load_data_from_file)
        self.load_file_button.setStyleSheet(
            "\n            QPushButton { \n                background-color: #5a5a5a; \n                color: #e0e0e0; \n                border: none; \n                border-radius: 5px; \n                padding: 10px 15px; \n                font-weight: bold; \n                min-width: 200px; \n            }\n            QPushButton:hover { \n                background-color: #6a6a6a; \n            }\n        "
        )
        file_load_buttons_vlayout.addWidget(self.load_file_button)
        self.howto_button = QPushButton("Как загрузить файл")
        self.howto_button.setStyleSheet(
            "\n            QPushButton { \n                background-color: #808080; \n                color: #ffffff; \n                border: none; \n                border-radius: 5px; \n                padding: 10px 15px; \n                font-weight: bold; \n                min-width: 200px; \n            }\n            QPushButton:hover { \n                background-color: #909090; \n            }\n        "
        )
        self.howto_button.clicked.connect(self.show_how_to_load_file_dialog)
        file_load_buttons_vlayout.addWidget(self.howto_button)
        buttons_layout.addLayout(file_load_buttons_vlayout)
        buttons_layout.addStretch()
        self.search_button = QPushButton("Поиск")
        self.search_button.setGraphicsEffect(self.search_button_opacity_effect)
        self.search_button.clicked.connect(self.perform_search)
        self.search_button.installEventFilter(self)
        self.search_button.setStyleSheet(
            "\n            QPushButton {\n                background-color: #4CAF50; /* Зеленый */\n                color: white;\n                border: none;\n                padding: 10px 20px;\n                border-radius: 5px;\n                font-weight: bold;\n                min-width: 100px;\n            }\n            QPushButton:hover { background-color: #45a049; }\n            QPushButton:pressed { background-color: #367c39; }\n        "
        )
        buttons_layout.addWidget(self.search_button)
        self.export_button = QPushButton("Экспорт результатов поиска")
        self.export_button.clicked.connect(self.export_results)
        buttons_layout.addWidget(self.export_button)
        main_layout.addLayout(buttons_layout)
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(6)
        self.results_table.setHorizontalHeaderLabels(
            [
                "№",
                "Автор",
                "Название материала",
                "Описание",
                "Дата решения",
                "Дата включения",
            ]
        )
        self.results_table.setWordWrap(True)
        font_height = self.results_table.fontMetrics().height()
        self.results_table.verticalHeader().setDefaultSectionSize(font_height * 3 + 10)
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.results_table.setSortingEnabled(False)
        self.results_table.horizontalHeader().sectionClicked.connect(
            self.on_header_clicked
        )
        self.results_table.itemActivated.connect(self.show_material_details)
        self.results_table.itemDoubleClicked.connect(self.show_material_details)
        self.results_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.results_table.setSelectionMode(QTableWidget.SingleSelection)
        main_layout.addWidget(self.results_table)
        status_container_layout = QHBoxLayout()
        self.status_label = QLabel("Готово к работе")
        self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        status_container_layout.addWidget(self.status_label)
        status_container_layout.addStretch()
        self.status_message_container.setLayout(QHBoxLayout())
        self.status_message_container.layout().setContentsMargins(0, 0, 0, 0)
        self.status_message_container.layout().setSpacing(5)
        self.status_message_container.layout().addWidget(self.status_message_label)
        self.status_minjust_button = QPushButton("Перейти на сайт МинЮста")
        self.status_minjust_button.clicked.connect(self.go_to_minjust_website)
        self.status_minjust_button.setStyleSheet(
            "\n            QPushButton { \n                background-color: #4a4a4a; \n                color: #e0e0e0; \n                border: none; \n                border-radius: 5px; \n                padding: 5px 10px; \n                font-weight: bold; \n            }\n            QPushButton:hover { \n                background-color: #5a5a5a; \n            }\n        "
        )
        self.status_minjust_button.hide()
        self.status_message_container.layout().addWidget(self.status_minjust_button)
        status_container_layout.addWidget(self.status_message_container)
        main_layout.addLayout(status_container_layout)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def eventFilter(self, obj, event):
        if obj == self.search_button:
            if event.type() == QEvent.Enter:
                self.on_search_button_enter(event)
                return True
            elif event.type() == QEvent.Leave:
                self.on_search_button_leave(event)
                return True
        return super().eventFilter(obj, event)

    def generate_rainbow_colors(self, num_colors=50):
        colors = []
        for i in range(num_colors):
            hue = i / num_colors
            color = QColor.fromHsvF(hue, 1.0, 1.0)
            colors.append(color)
        return colors

    def setup_search_button_animation(self):
        self.rainbow_timer.timeout.connect(self.update_rainbow_color)
        self.rainbow_timer.start(30)
        self.pulsating_animation.setDuration(1000)
        self.pulsating_animation.setLoopCount(-1)
        self.pulsating_animation.setEasingCurve(QEasingCurve.InOutSine)
        self.pulsating_animation.setStartValue(1.0)
        self.pulsating_animation.setEndValue(0.7)
        self.pulsating_animation.start()

    def update_rainbow_color(self):
        color = self.rainbow_colors[self.current_rainbow_color_index]
        self.search_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #d17a3a;
                color: {color.name()};
                border: none;
                border-radius: 5px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 12pt;
            }}
            QPushButton:hover {{
                background-color: #e08b47;
            }}
            QPushButton:pressed {{
                background-color: #c06929;
            }}
        """
        )
        self.current_rainbow_color_index = (self.current_rainbow_color_index + 1) % len(
            self.rainbow_colors
        )

    def on_search_button_enter(self, event):
        self.rainbow_timer.setInterval(10)
        self.pulsating_animation.start()

    def on_search_button_leave(self, event):
        self.rainbow_timer.setInterval(30)
        self.pulsating_animation.stop()
        self.search_button_opacity_effect.setOpacity(1.0)

    def setup_status_message_animation(self):
        self.status_alpha_animation.setDuration(1000)
        self.status_alpha_animation.setStartValue(1.0)
        self.status_alpha_animation.setEndValue(0.5)
        self.status_alpha_animation.setLoopCount(-1)
        self.status_alpha_animation.setEasingCurve(QEasingCurve.InOutSine)
        self.status_message_label.hide()
        self.status_minjust_button.hide()

    def _update_status_label_color(self, color):
        self.status_message_label.setStyleSheet(
            f"color: {color.name()}; font-weight: bold; font-size: 18pt;"
        )

    def display_search_status(self, found_count):
        self.status_alpha_animation.stop()
        self.status_message_label.show()
        self.status_label_opacity_effect.setOpacity(1.0)
        if found_count > 0:
            self.status_message_label.setText("ЗАПРЕЩЕНО")
            self.status_message_label.setStyleSheet(
                "color: red; font-weight: bold; font-size: 18pt;"
            )
            self.status_minjust_button.hide()
            self.status_alpha_animation.start()
        else:
            self.status_message_label.setText("Пока не запрещено")
            self.status_message_label.setStyleSheet(
                "color: orange; font-weight: bold; font-size: 10pt;"
            )
            self.status_minjust_button.show()
            self.status_alpha_animation.stop()
            self.status_label_opacity_effect.setOpacity(1.0)

    def on_header_clicked(self, logical_index):
        if logical_index not in [0, 5]:
            return
        column_map = {0: "id", 5: "entry_date"}
        sort_key = column_map[logical_index]
        is_date = sort_key == "entry_date"
        if self.current_sort_column == logical_index:
            self.current_sort_order = (
                Qt.DescendingOrder
                if self.current_sort_order == Qt.AscendingOrder
                else Qt.AscendingOrder
            )
        else:
            self.current_sort_column = logical_index
            self.current_sort_order = Qt.AscendingOrder
        self.sort_data(sort_key, self.current_sort_order, is_date=is_date)

    def sort_data(self, key, order, is_date=False):
        if not self.filtered_data:
            return

        def get_sort_value(item):
            value = item.get(key)
            if value is None:
                return datetime.datetime.min if is_date else ""
            if key == "id":
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return sys.maxsize
            if is_date:
                try:
                    return datetime.datetime.strptime(value, "%d.%m.%Y")
                except (ValueError, TypeError):
                    return datetime.datetime.min
            return str(value).lower()

        self.filtered_data.sort(key=get_sort_value, reverse=order == Qt.DescendingOrder)
        self.update_results_table()

    def extract_material_category(self, description):
        desc_lower = description.lower()
        book_keywords = [
            "книга",
            "книги",
            "брошюра",
            "учебник",
            "печатный материал",
            "монография",
            "альманах",
            "печатный",
            "e-book",
            "книжка",
            "том",
        ]
        if any(keyword in desc_lower for keyword in book_keywords):
            return "Книги/Брошюры"
        journal_keywords = [
            "журнал",
            "периодическое издание",
            "дайджест",
            "сборник статей",
        ]
        if any(keyword in desc_lower for keyword in journal_keywords):
            return "Журналы"
        newspaper_keywords = [
            "газета",
            "пресса",
            "еженедельник",
            "вестник",
            "статья из газеты",
        ]
        if any(keyword in desc_lower for keyword in newspaper_keywords):
            return "Газеты"
        leaflet_keywords = [
            "листовка",
            "буклет",
            "памятка",
            "открытка",
            "флаер",
            "плакат",
            "стикер",
            "наклейка",
            "баннер",
            "агитационный материал",
        ]
        if any(keyword in desc_lower for keyword in leaflet_keywords):
            return "Листовки/Буклеты/Памятки"
        audio_keywords = [
            "аудиозапись",
            "песня",
            "фонограмма",
            "аудио",
            "трек",
            "звуковой файл",
            "подкаст",
            "музыкальная композиция",
            "музыка",
        ]
        audio_extensions = ["mp3", "wav", "flac", "ogg", "aac", "m4a", "wma"]
        if any(keyword in desc_lower for keyword in audio_keywords) or any(
            f".{ext}" in desc_lower for ext in audio_extensions
        ):
            return "Аудиозаписи"
        video_keywords = [
            "видеозапись",
            "фильм",
            "ролик",
            "видеоматериал",
            "видео",
            "видеоклип",
            "кинофильм",
            "видеоролик",
            "мультфильм",
            "сюжет",
            "трансляция",
        ]
        video_extensions = ["avi", "mp4", "mov", "wmv", "mkv", "flv"]
        if any(keyword in desc_lower for keyword in video_keywords) or any(
            f".{ext}" in desc_lower for ext in video_extensions
        ):
            return "Видеозаписи"
        image_keywords = [
            "изображение",
            "фотография",
            "рисунок",
            "картинка",
            "фото",
            "графический файл",
            "демонстрационный материал",
            "коллаж",
            "мем",
            "карикатура",
        ]
        image_extensions = ["jpg", "jpeg", "png", "gif", "bmp", "webp"]
        if any(keyword in desc_lower for keyword in image_keywords) or any(
            f".{ext}" in desc_lower for ext in image_extensions
        ):
            return "Изображения/Фото"
        web_keywords = [
            "сайт",
            "веб-страница",
            "интернет-ресурс",
            "онлайн",
            "социальная сеть",
            "telegram",
            "vkontakte",
            "мессенджер",
            "форум",
            "блог",
            "канал",
            "сообщество",
            "url",
            "ссылка",
            "веб-сайт",
            "интернет-портал",
            "youtube",
            "vk",
            "twitter",
            "facebook",
            "instagram",
        ]
        if any(keyword in desc_lower for keyword in web_keywords) or re.search(
            "(https?|ftp)://", desc_lower
        ):
            return "Веб-материалы"
        software_keywords = [
            "программа",
            "приложение",
            "по",
            "софт",
            "исполняемый файл",
            "скрипт",
            "код",
            "программное обеспечение",
            "вирус",
        ]
        software_extensions = [
            "exe",
            "apk",
            "dmg",
            "iso",
            "zip",
            "rar",
            "7z",
            "dll",
            "bin",
            "sh",
            "bat",
            "py",
            "js",
        ]
        if any(keyword in desc_lower for keyword in software_keywords) or any(
            f".{ext}" in desc_lower for ext in software_extensions
        ):
            return "Программы/ПО"
        text_document_keywords = [
            "статья",
            "публикация",
            "текст",
            "документ",
            "рукопись",
            "записка",
            "письмо",
        ]
        if any(keyword in desc_lower for keyword in text_document_keywords):
            return "Статьи/Тексты"
        return "Прочее"

    def parse_csv_content(self, content):
        parsed_data = []
        new_index = {
            "material_title": [],
            "author": [],
            "description": [],
            "date": [],
            "court": [],
            "category": [],
            "file_info": [],
        }
        found_categories = set()
        seen_ids = set()
        f = StringIO(content)
        reader = csv.reader(f, delimiter=";", quotechar='"')
        for row in reader:
            try:
                if not row or not row[0].strip().isdigit():
                    continue
                item_id = row[0].strip()
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                original_full_description = row[1].strip() if len(row) > 1 else ""
                work_description = original_full_description
                date_inclusion = (
                    row[2].strip()
                    if len(row) > 2
                    and re.match("\\d{2}\\.\\d{2}\\.\\d{4}", row[2].strip())
                    else "Неизвестна"
                )
                court_decision = "Неизвестен"
                decision_date = "Неизвестна"
                court_name = "Неизвестен"
                court_match = re.search("\\((решени[ея].*?)\\);?$", work_description)
                if court_match:
                    court_decision = court_match.group(1).strip()
                    work_description = work_description[: court_match.start()].strip()
                    date_match = re.search(
                        "от\\s+(\\d{2}\\.\\d{2}\\.\\d{4})", court_decision
                    )
                    if date_match:
                        decision_date = date_match.group(1)
                        court_name_full = re.search(
                            "^(.*?)\\sот\\s+\\d{2}\\.\\d{2}\\.\\d{4}", court_decision
                        )
                        if court_name_full:
                            court_name = (
                                court_name_full.group(1)
                                .replace("решение", "")
                                .replace("решением", "")
                                .strip()
                            )
                    else:
                        court_name = court_decision
                author = "Неизвестен"
                material_title = "Без названия"
                quoted_text_match = re.search("«([^»]+)»", work_description)
                if quoted_text_match:
                    full_quoted_text = quoted_text_match.group(1).strip()
                    publisher_match = re.search(
                        "^(.*?)(?:\\s*[–-]\\s*(?:Издательство|Verlag|Publishing).*)",
                        full_quoted_text,
                    )
                    if publisher_match:
                        clean_title = publisher_match.group(1).strip().rstrip(",.")
                    else:
                        clean_title = full_quoted_text
                    material_title = clean_title
                    author_keyword_match = re.search(
                        '(?:автора|исполнителя)\\s+([^«"]+)',
                        work_description,
                        re.IGNORECASE,
                    )
                    if author_keyword_match:
                        author = (
                            author_keyword_match.group(1).strip().rstrip("«").strip()
                        )
                    elif "имя автора" in work_description.lower():
                        author_in_title_match = re.match(
                            "^([\\w\\s-]+?\\.)\\s+([\\w\\s\\W]+)", clean_title
                        )
                        if author_in_title_match:
                            author = author_in_title_match.group(1).strip().rstrip(".")
                            material_title = author_in_title_match.group(2).strip()
                category = self.extract_material_category(original_full_description)
                found_categories.add(category)
                display_description = (
                    work_description[:200] + "..."
                    if len(work_description) > 200
                    else work_description
                )
                parsed_data.append(
                    {
                        "id": item_id,
                        "material_title": material_title,
                        "author_or_publisher": author,
                        "description": display_description,
                        "original_description": original_full_description,
                        "entry_date": date_inclusion,
                        "links": [],
                        "court_decision": court_decision,
                        "decision_date": decision_date,
                        "court_name": court_name,
                        "category": category,
                        "file_info": "Не указано",
                    }
                )
                new_index["material_title"].append(material_title.lower())
                new_index["author"].append(author.lower())
                new_index["description"].append(work_description.lower())
                new_index["date"].append(date_inclusion.lower())
                new_index["court"].append(court_decision.lower())
                new_index["category"].append(category.lower())
                new_index["file_info"].append("не указано")
            except (IndexError, Exception):
                continue
        sorted_categories = sorted(list(found_categories))
        sorted_categories.insert(0, "Все категории")
        return parsed_data, new_index, sorted_categories

    def parse_rss_content(self, content):
        soup = BeautifulSoup(content, "xml")
        items = soup.find_all("item")
        parsed_data = []
        new_index = {
            "material_title": [],
            "author": [],
            "description": [],
            "date": [],
            "court": [],
            "category": [],
            "file_info": [],
        }
        found_categories = set()
        seen_ids = set()
        for item in items:
            try:
                guid = item.guid.text.strip() if item.guid else None
                title_text = item.title.text.strip() if item.title else ""
                item_id_from_title = re.match("^\\s*(\\d+)", title_text)
                item_id = item_id_from_title.group(1) if item_id_from_title else guid
                if not item_id or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                date_inclusion = "Неизвестна"
                if item.pubDate and item.pubDate.text:
                    try:
                        pub_date = datetime.datetime.strptime(
                            item.pubDate.text, "%a, %d %b %Y %H:%M:%S %z"
                        )
                        date_inclusion = pub_date.strftime("%d.%m.%Y")
                    except ValueError:
                        pass
                original_full_description = BeautifulSoup(
                    item.description.text if item.description else "", "html.parser"
                ).get_text(separator=" ", strip=True)
                work_description = original_full_description
                court_decision = "Неизвестен"
                decision_date = "Неизвестна"
                court_name = "Неизвестен"
                court_match = re.search("\\((решени[ея].*?)\\)$", work_description)
                if court_match:
                    court_decision = court_match.group(1).strip()
                    work_description = work_description[: court_match.start()].strip()
                    date_match = re.search(
                        "от\\s+(\\d{2}\\.\\d{2}\\.\\d{4})", court_decision
                    )
                    if date_match:
                        decision_date = date_match.group(1)
                        court_name_full = re.search(
                            "^(.*?)\\sот\\s+\\d{2}\\.\\d{2}\\.\\d{4}", court_decision
                        )
                        if court_name_full:
                            court_name = (
                                court_name_full.group(1)
                                .replace("решение", "")
                                .replace("решением", "")
                                .strip()
                            )
                    else:
                        court_name = court_decision
                material_title = re.sub("^\\d+:\\s*", "", title_text)
                author = "Неизвестен"
                author_keyword_match = re.search(
                    '(?:автора|исполнителя)\\s+([^«"]+)',
                    work_description,
                    re.IGNORECASE,
                )
                if author_keyword_match:
                    author = author_keyword_match.group(1).strip().rstrip("«").strip()
                category = self.extract_material_category(original_full_description)
                found_categories.add(category)
                link = item.link.text if item.link else ""
                display_description = (
                    work_description[:200] + "..."
                    if len(work_description) > 200
                    else work_description
                )
                parsed_data.append(
                    {
                        "id": item_id,
                        "material_title": material_title,
                        "author_or_publisher": author,
                        "description": display_description,
                        "original_description": original_full_description,
                        "entry_date": date_inclusion,
                        "links": [link] if link else [],
                        "court_decision": court_decision,
                        "decision_date": decision_date,
                        "court_name": court_name,
                        "category": category,
                        "file_info": "Не указано",
                    }
                )
                new_index["material_title"].append(material_title.lower())
                new_index["author"].append(author.lower())
                new_index["description"].append(work_description.lower())
                new_index["date"].append(date_inclusion.lower())
                new_index["court"].append(court_decision.lower())
                new_index["category"].append(category.lower())
                new_index["file_info"].append("не указано")
            except Exception:
                continue
        sorted_categories = sorted(list(found_categories))
        sorted_categories.insert(0, "Все категории")
        return parsed_data, new_index, sorted_categories

    def decode_content_robust(self, content_bytes):
        for encoding in ENCODINGS_TO_TRY:
            try:
                decoded = content_bytes.decode(encoding)
                if any(ord(c) > 127 for c in decoded) and "юст" in decoded.lower():
                    return decoded
            except UnicodeDecodeError:
                continue
        raise UnicodeDecodeError(
            "Unable to decode content with any of the tried encodings."
        )

    def load_data_from_web(self):
        self.status_label.setText("Загрузка данных из интернета (RSS)...")
        QApplication.processEvents()
        try:
            response = requests.get(RSS_URL, verify=False, timeout=30)
            response.raise_for_status()
            decoded_content = self.decode_content_robust(response.content)
            self.data, self.index, updated_categories = self.parse_rss_content(
                decoded_content
            )
            self.update_category_filter(updated_categories)
            self.filtered_data = self.data.copy()
            self.update_results_table()
            self.status_label.setText(
                f"Загружено {len(self.data)} записей из RSS-ленты."
            )
            self.save_data()
            return True
        except Exception as e:
            self.status_label.setText(
                f"Ошибка загрузки RSS: {str(e)}. Попытка загрузки CSV..."
            )
            QApplication.processEvents()
            return self.load_csv_from_web_smart()

    def load_csv_from_web_smart(self):
        self.status_label.setText("Попытка загрузки CSV из интернета (requests)...")
        QApplication.processEvents()
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
                "Referer": "https://minjust.gov.ru/ru/extremist-materials/",
            }
            response = requests.get(CSV_URL, headers=headers, verify=False, timeout=30)
            response.raise_for_status()
            decoded_content = self.decode_content_robust(response.content)
            self.data, self.index, updated_categories = self.parse_csv_content(
                decoded_content
            )
            self.update_category_filter(updated_categories)
            self.filtered_data = self.data.copy()
            self.update_results_table()
            self.status_label.setText(
                f"Загружено {len(self.data)} записей из CSV-файла."
            )
            self.save_data()
            return True
        except Exception as e:
            self.status_label.setText(
                f"Ошибка загрузки CSV (requests): {str(e)}. Попытка через wget/curl..."
            )
            QApplication.processEvents()
            return self.load_csv_from_web_cli()

    def load_csv_from_web_cli(self):
        self.status_label.setText(
            "Попытка загрузки CSV через командную строку (wget/curl)..."
        )
        QApplication.processEvents()
        temp_csv_file = "temp_minjust_export.csv"
        command = []
        if platform.system() == "Windows":
            try:
                subprocess.run(["curl", "--version"], capture_output=True, check=True)
                command = [
                    "curl",
                    "-k",
                    "-o",
                    temp_csv_file,
                    CSV_URL,
                    "-H",
                    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "-H",
                    "Referer: https://minjust.gov.ru/ru/extremist-materials/",
                ]
            except (subprocess.CalledProcessError, FileNotFoundError):
                try:
                    subprocess.run(
                        ["wget", "--version"], capture_output=True, check=True
                    )
                    command = [
                        "wget",
                        "--no-check-certificate",
                        "-O",
                        temp_csv_file,
                        CSV_URL,
                        "--header=User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                        "--header=Referer: https://minjust.gov.ru/ru/extremist-materials/",
                    ]
                except (subprocess.CalledProcessError, FileNotFoundError):
                    self.status_label.setText(
                        "Ошибка: wget или curl не найдены. Не удалось загрузить CSV через CLI."
                    )
                    return False
        else:
            try:
                subprocess.run(["wget", "--version"], capture_output=True, check=True)
                command = [
                    "wget",
                    "--no-check-certificate",
                    "-O",
                    temp_csv_file,
                    CSV_URL,
                    "--header=User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "--header=Referer: https://minjust.gov.ru/ru/extremist-materials/",
                ]
            except (subprocess.CalledProcessError, FileNotFoundError):
                try:
                    subprocess.run(
                        ["curl", "--version"], capture_output=True, check=True
                    )
                    command = [
                        "curl",
                        "-k",
                        "-o",
                        temp_csv_file,
                        CSV_URL,
                        "-H",
                        "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                        "-H",
                        "Referer: https://minjust.gov.ru/ru/extremist-materials/",
                    ]
                except (subprocess.CalledProcessError, FileNotFoundError):
                    self.status_label.setText(
                        "Ошибка: wget или curl не найдены. Не удалось загрузить CSV через CLI."
                    )
                    return False
        if not command:
            return False
        try:
            subprocess.run(command, check=True, capture_output=True, text=False)
            with open(temp_csv_file, "rb") as f:
                content_bytes = f.read()
            decoded_content = self.decode_content_robust(content_bytes)
            self.data, self.index, updated_categories = self.parse_csv_content(
                decoded_content
            )
            self.update_category_filter(updated_categories)
            self.filtered_data = self.data.copy()
            self.update_results_table()
            self.status_label.setText(
                f"Загружено {len(self.data)} записей из CSV-файла (CLI)."
            )
            self.save_data()
            os.remove(temp_csv_file)
            return True
        except Exception as e:
            self.status_label.setText(f"Ошибка загрузки CSV (CLI): {str(e)}")
            if os.path.exists(temp_csv_file):
                os.remove(temp_csv_file)
            return False

    def load_data_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл данных (CSV/XML/RSS)",
            "",
            "Data Files (*.csv *.xml *.rss *.txt);;All Files (*)",
        )
        if file_path:
            try:
                with open(file_path, "rb") as f:
                    content_bytes = f.read()
                decoded_content = self.decode_content_robust(content_bytes)
                if file_path.lower().endswith((".csv", ".txt")):
                    self.data, self.index, updated_categories = self.parse_csv_content(
                        decoded_content
                    )
                else:
                    self.data, self.index, updated_categories = self.parse_rss_content(
                        decoded_content
                    )
                self.update_category_filter(updated_categories)
                self.filtered_data = self.data.copy()
                self.update_results_table()
                current_date = datetime.date.today().strftime("%d.%m.%Y")
                self.status_label.setText(
                    f"Загружено {len(self.data)} записей из файла, данные актуальны на <span style='color: orange;'>{current_date}</span>"
                )
                self.status_label.setStyleSheet("")
                self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                self.save_data()
            except Exception as e:
                self.status_label.setText(
                    f"Ошибка загрузки или обработки файла: {str(e)}"
                )
                self.status_label.setStyleSheet("QLabel { color: red; }")
                self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def save_data(self):
        try:
            with open(DATA_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.status_label.setText(f"Ошибка сохранения данных: {str(e)}")

    def load_saved_data(self):
        if os.path.exists(DATA_FILE_PATH):
            try:
                with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                self.index = {
                    "material_title": [],
                    "author": [],
                    "description": [],
                    "date": [],
                    "court": [],
                    "category": [],
                    "file_info": [],
                }
                found_categories = set()
                for (i, item) in enumerate(self.data):
                    item.setdefault("id", str(i + 1))
                    item.setdefault("material_title", "Без названия")
                    item.setdefault("author_or_publisher", "Неизвестен")
                    item.setdefault("description", "")
                    item.setdefault("original_description", item.get("description", ""))
                    item.setdefault("entry_date", "Неизвестна")
                    item.setdefault("links", [])
                    item.setdefault("court_decision", "Неизвестен")
                    item.setdefault("decision_date", "Неизвестна")
                    item.setdefault("court_name", "Неизвестен")
                    item.setdefault(
                        "category",
                        self.extract_material_category(
                            item.get("original_description", "")
                            + " "
                            + item.get("material_title", "")
                        ),
                    )
                    item.setdefault("file_info", "Не указано")
                    self.index["material_title"].append(
                        item.get("material_title", "").lower()
                    )
                    self.index["author"].append(
                        item.get("author_or_publisher", "").lower()
                    )
                    self.index["description"].append(
                        item.get("original_description", "").lower()
                    )
                    self.index["date"].append(item.get("entry_date", "").lower())
                    self.index["court"].append(item.get("court_decision", "").lower())
                    self.index["category"].append(item.get("category", "").lower())
                    self.index["file_info"].append(item.get("file_info", "").lower())
                    found_categories.add(item["category"])
                sorted_categories = sorted(list(found_categories))
                sorted_categories.insert(0, "Все категории")
                self.update_category_filter(sorted_categories)
                self.filtered_data = self.data.copy()
                self.filtered_data.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
                self.update_results_table()
                self.status_label.setText(
                    f"Загружено {len(self.data)} записей из сохраненного файла."
                )
                return True
            except Exception as e:
                self.status_label.setText(
                    f"Ошибка загрузки сохраненных данных: {str(e)}"
                )
                if os.path.exists(DATA_FILE_PATH):
                    os.remove(DATA_FILE_PATH)
                return False
        return False

    def update_category_filter(self, new_categories):
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItems(new_categories)
        self.category_filter.blockSignals(False)

    def perform_search(self):
        query = self.search_input.text().lower().strip()
        selected_category = self.category_filter.currentText()
        if not query and selected_category == "Все категории":
            self.status_label.setText(
                "Введите поисковый запрос или выберите категорию."
            )
            return
        selected_criteria = self.search_criteria.currentText()
        self.filtered_data = []
        for (i, item) in enumerate(self.data):
            if (
                selected_category != "Все категории"
                and item.get("category", "").lower() != selected_category.lower()
            ):
                continue
            if query:
                match = False
                if selected_criteria == "Все поля":
                    if (
                        query in self.index["material_title"][i]
                        or query in self.index["author"][i]
                        or query in self.index["description"][i]
                        or query in self.index["date"][i]
                        or query in self.index["court"][i]
                        or query in self.index["category"][i]
                        or query in self.index["file_info"][i]
                    ):
                        match = True
                elif selected_criteria == "Номер" and query == item.get("id"):
                    match = True
                elif (
                    selected_criteria == "Название материала"
                    and query in self.index["material_title"][i]
                ):
                    match = True
                elif selected_criteria == "Автор" and query in self.index["author"][i]:
                    match = True
                elif (
                    selected_criteria == "Описание"
                    and query in self.index["description"][i]
                ):
                    match = True
                elif (
                    selected_criteria == "Дата включения"
                    and query in self.index["date"][i]
                ):
                    match = True
                elif selected_criteria == "Суд" and query in self.index["court"][i]:
                    match = True
                elif (
                    selected_criteria == "Категория"
                    and query in self.index["category"][i]
                ):
                    match = True
                if match:
                    self.filtered_data.append(item)
            else:
                self.filtered_data.append(item)
        if self.current_sort_column != -1:
            column_map = {
                0: "id",
                1: "material_title",
                2: "author_or_publisher",
                3: "original_description",
                5: "entry_date",
            }
            sort_key = column_map.get(self.current_sort_column)
            if sort_key:
                self.sort_data(
                    sort_key, self.current_sort_order, is_date=sort_key == "entry_date"
                )
            else:
                self.update_results_table()
        else:
            self.update_results_table()
        self.display_search_status(len(self.filtered_data))

    def update_results_table(self):
        self.results_table.setRowCount(len(self.filtered_data))
        for (row, item) in enumerate(self.filtered_data):
            self.results_table.setItem(
                row, 0, QTableWidgetItem(str(item.get("id", "N/A")))
            )
            author_item = QTableWidgetItem(
                item.get("author_or_publisher", "Неизвестен")
            )
            author_item.setFlags(author_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 1, author_item)
            title_item = QTableWidgetItem(item.get("material_title", "Не указано"))
            title_item.setFlags(title_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 2, title_item)
            description_str = item.get("description", "Отсутствует")
            original_description_for_tooltip = item.get(
                "original_description", description_str
            )
            desc_item = QTableWidgetItem(description_str)
            desc_item.setToolTip(original_description_for_tooltip)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 3, desc_item)
            decision_date_item = QTableWidgetItem(
                item.get("decision_date", "Неизвестна")
            )
            decision_date_item.setFlags(decision_date_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 4, decision_date_item)
            entry_date_item = QTableWidgetItem(item.get("entry_date", "Неизвестна"))
            entry_date_item.setFlags(entry_date_item.flags() & ~Qt.ItemIsEditable)
            self.results_table.setItem(row, 5, entry_date_item)
        self.results_table.verticalHeader().setVisible(False)

    def show_material_details(self, item_table_widget):
        if isinstance(item_table_widget, QTableWidgetItem):
            row_index = item_table_widget.row()
        else:
            row_index = self.results_table.row(item_table_widget)
        if 0 <= row_index < len(self.filtered_data):
            selected_material = self.filtered_data[row_index]
            dialog = MaterialDetailDialog(self, selected_material)
            dialog.exec_()

    def export_results(self):
        if not self.filtered_data:
            self.status_label.setText("Нет данных для экспорта")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт результатов",
            "",
            "Текстовые файлы (*.txt);;CSV файлы (*.csv);;HTML файлы (*.html)",
        )
        if file_path:
            try:
                if file_path.endswith(".csv"):
                    with open(file_path, "w", encoding="utf-8", newline="") as f:
                        writer = csv.writer(f, delimiter=";")
                        writer.writerow(
                            [
                                "№",
                                "Название материала",
                                "Автор/Издатель",
                                "Полное описание",
                                "Дата включения",
                                "Суд",
                                "Категория",
                                "Ссылки",
                            ]
                        )
                        for item in self.filtered_data:
                            desc = (
                                item.get("original_description", "")
                                .replace("\n", " ")
                                .replace("\r", " ")
                                .replace(";", ",")
                            )
                            links = ", ".join(item.get("links", []))
                            writer.writerow(
                                [
                                    item.get("id", "N/A"),
                                    item.get("material_title", "Без названия"),
                                    item.get("author_or_publisher", "Неизвестен"),
                                    desc,
                                    item.get("entry_date", "Неизвестна"),
                                    item.get("court_name", "Неизвестен"),
                                    item.get("category", "Прочее"),
                                    links,
                                ]
                            )
                elif file_path.endswith(".html"):
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(
                            "<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n<title>Экстремистские материалы</title>\n<style>\nbody { font-family: 'Ubuntu', sans-serif; background-color: #2b2b2b; color: #e0e0e0; }\ntable { width: 100%; border-collapse: collapse; margin-top: 20px; }\nth, td { border: 1px solid #505050; padding: 8px; text-align: left; }\nth { background-color: #3c3c3c; color: #d17a3a; }\ntr:nth-child(even) { background-color: #353535; }\na { color: #e08b47; text-decoration: none; }\na:hover { text-decoration: underline; }\n</style>\n</head>\n<body>\n<h1>Список экстремистских материалов</h1>\n<table>\n<thead>\n<tr><th>№</th><th>Название материала</th><th>Автор/Издатель</th><th>Описание</th><th>Дата включения</th><th>Суд</th><th>Категория</th><th>Ссылки</th></tr>\n</thead>\n<tbody>\n"
                        )
                        for item in self.filtered_data:
                            html_escape = (
                                lambda s: str(s)
                                .replace("&", "&amp;")
                                .replace("<", "&lt;")
                                .replace(">", "&gt;")
                                .replace('"', "&quot;")
                                .replace("'", "&#39;")
                            )
                            item_id_html = html_escape(item.get("id", "N/A"))
                            title_html = html_escape(
                                item.get("material_title", "Без названия")
                            )
                            author_html = html_escape(
                                item.get("author_or_publisher", "Неизвестен")
                            )
                            desc_html = html_escape(
                                item.get("original_description", "")
                            )
                            date_html = html_escape(
                                item.get("entry_date", "Неизвестна")
                            )
                            court_html = html_escape(
                                item.get("court_name", "Неизвестен")
                            )
                            category_html = html_escape(item.get("category", "Прочее"))
                            links_list = item.get("links", [])
                            links_html = ", ".join(
                                [
                                    f'<a href="{html_escape(link)}" target="_blank">{html_escape(link)}</a>'
                                    for link in links_list
                                ]
                            )
                            f.write(
                                f"<tr><td>{item_id_html}</td><td>{title_html}</td><td>{author_html}</td><td>{desc_html}</td><td>{date_html}</td><td>{court_html}</td><td>{category_html}</td><td>{links_html}</td></tr>\n"
                            )
                        f.write("</tbody>\n</table>\n</body>\n</html>")
                else:
                    with open(file_path, "w", encoding="utf-8") as f:
                        for item in self.filtered_data:
                            f.write(f"№: {item.get('id','N/A')}\n")
                            f.write(
                                f"Название материала: {item.get('material_title','Без названия')}\n"
                            )
                            f.write(
                                f"Автор/Издатель: {item.get('author_or_publisher','Неизвестен')}\n"
                            )
                            f.write(
                                f"Описание: {item.get('original_description','')}\n"
                            )
                            f.write(
                                f"Включено: {item.get('entry_date','Неизвестна')}\n"
                            )
                            f.write(f"Решение: {item.get('court_name','Неизвестен')}\n")
                            f.write(f"Категория: {item.get('category','Прочее')}\n")
                            links = ", ".join(item.get("links", []))
                            f.write(f"Ссылки: {links}\n")
                            f.write("-" * 50 + "\n")
                self.status_label.setText(f"Результаты экспортированы в {file_path}")
            except Exception as e:
                self.status_label.setText(f"Ошибка экспорта: {str(e)}")

    def show_howto_wtf_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("О программе и помощь")
        dialog.setGeometry(self.x() + 100, self.y() + 100, 700, 500)
        dialog.setStyleSheet(self.get_dark_theme_stylesheet())
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        layout = QVBoxLayout(dialog)
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        text_browser.setStyleSheet(
            "background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #505050; padding: 15px; border-radius: 5px;"
        )
        text_browser.setHtml(
            '\n            <h2 style="color: #d17a3a; text-align: center;">Добро пожаловать в Федеральный список экстремистских материалов</h2>\n            <p>Это приложение позволяет удобно просматривать и искать информацию о материалах, включенных в Федеральный список экстремистских материалов Министерства юстиции Российской Федерации.</p>\n            <p><strong>Основные функции:</strong></p>\n            <ul style="margin-left: 15px;">\n                <li><strong>Загрузка данных:</strong> Автоматическая загрузка актуальных данных с официального сайта МинЮста (сначала RSS, затем попытка CSV через requests, wget/curl). Также возможна загрузка из локального RSS/XML/CSV файла.</li>\n                <li><strong>Поиск:</strong> Быстрый поиск по названию материала, автору, описанию, дате включения, суду или категории. Поиск активируется по нажатию Enter в поле ввода.</li>\n                <li><strong>Фильтр по категориям:</strong> Удобный фильтр по типу материала (например, "Книги/Брошюры", "Аудиозаписи" и т.д.), извлеченному из описания.</li>\n                <li><strong>Сортировка:</strong> Таблица поддерживает сортировку по "№", "Названию материала", "Автору" и "Дате включения" (от новых к старым, от старых к новым) при клике на заголовок столбца.</li>\n                <li><strong>Экспорт:</strong> Экспорт отфильтрованных результатов в текстовый, CSV или HTML-файл.</li>\n                <li><strong>Сохранение данных:</strong> Приложение автоматически сохраняет загруженные данные в файл <code>extremist_materials_data.json</code> для быстрого доступа при следующем запуске, чтобы избежать повторной загрузки из сети.</li>\n                <li><strong>Подробный просмотр:</strong> Выберите строку в таблице и нажмите <strong>Enter</strong> (или дважды кликните мышью), чтобы открыть окно с полной информацией о материале.</li>\n                <li><strong>Изменение ширины столбцов:</strong> Вы можете перетаскивать границы заголовков столбцов в таблице, чтобы изменить их ширину по своему усмотрению. Столбцы будут автоматически масштабироваться, чтобы оставаться в пределах окна.</li>\n            </ul>\n            <p><strong>Что это за софтина?</strong></p>\n            <p>Данное ПО разработано для облегчения доступа к публичной информации, предоставляемой Министерством юстиции РФ, и не является официальным продуктом МинЮста. Все данные берутся из открытых RSS- и CSV-потоков.</p>\n        '
        )
        layout.addWidget(text_browser)
        close_button = QPushButton("Закрыть")
        close_button.setStyleSheet(
            "\n            QPushButton { \n                background-color: #d17a3a; \n                color: #ffffff; \n                border: none; \n                border-radius: 5px; \n                padding: 10px 15px; \n                font-weight: bold; \n            }\n            QPushButton:hover { \n                background-color: #e08b47; \n            }\n            QPushButton:pressed {\n                background-color: #c06929;\n            }\n        "
        )
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=Qt.AlignCenter)
        dialog.exec_()

    def show_how_to_load_file_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Инструкция: Как найти и загрузить файл")
        dialog.setGeometry(self.x() + 200, self.y() + 200, 600, 400)
        dialog.setStyleSheet(self.get_dark_theme_stylesheet())
        dialog.setModal(True)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        dialog_layout = QVBoxLayout(dialog)
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        text_browser.setStyleSheet(
            "background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #505050; padding: 15px; border-radius: 5px;"
        )
        text_browser.setHtml(
            f"""
            <h2 style="color: #d17a3a; text-align: center;">Как сохранить RSS/CSV файл с сайта МинЮста</h2>
            <p>Вы можете загрузить данные из локального файла, если у вас возникли проблемы с прямым доступом к сайту или вы хотите работать с оффлайн-копией.</p>
            <p><strong>Для RSS-файла (<a href="{RSS_URL}" target="_blank" style="color: #e08b47;">{RSS_URL}</a>):</strong></p>
            <ol style="margin-left: 15px;">
                <li>Перейдите по ссылке RSS-потока в браузере.</li>
                <li>Когда страница с XML-данными откроется, нажмите <code>Ctrl+S</code> (или <code>Command+S</code> на Mac).</li>
                <li>В диалоговом окне сохранения, выберите "Веб-страница, только HTML" или "Все файлы", и введите имя файла с расширением <code>.xml</code>, <code>.rss</code> или <code>.txt</code> (например, <code>extremist_materials.xml</code>).</li>
                <li>Сохраните файл.</li>
            </ol>
            <p><strong>Для CSV-файла (<a href="{CSV_URL}" target="_blank" style="color: #e08b47;">{CSV_URL}</a>):</strong></p>
            <ol style="margin-left: 15px;">
                <li>Перейдите по ссылке CSV-файла в браузере.</li>
                <li>Ваш браузер может предложить сразу скачать файл или отобразить его текст. Если отобразил текст, нажмите <code>Ctrl+S</code> (или <code>Command+S</code>) и сохраните как <code>.csv</code> или <code>.txt</code>.</li>
                <li>Если файл скачался автоматически, он будет в вашей папке загрузок.</li>
            </ol>
            <p>После сохранения, в приложении нажмите кнопку <strong>"Загрузить из файла (CSV/XML)"</strong> и выберите сохраненный вами файл.</p>
        """
        )
        dialog_layout.addWidget(text_browser)
        close_button = QPushButton("Закрыть")
        close_button.setStyleSheet(
            "\n            QPushButton { \n                background-color: #d17a3a; \n                color: #ffffff; \n                border: none; \n                border-radius: 5px; \n                padding: 10px 15px; \n                font-weight: bold; \n            }\n            QPushButton:hover { \n                background-color: #e08b47; \n            }\n            QPushButton:pressed {\n                background-color: #c06929;\n            }\n        "
        )
        close_button.clicked.connect(dialog.accept)
        dialog_layout.addWidget(close_button, alignment=Qt.AlignCenter)
        dialog.exec_()

    def go_to_minjust_website(self):
        QDesktopServices.openUrl(QUrl("https://minjust.gov.ru/ru/extremist-materials/"))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ExtrimistMaterialsApp()
    window.show()
    sys.exit(app.exec_())
