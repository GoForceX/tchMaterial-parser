# -*- coding: utf-8 -*-
# 国家中小学智慧教育平台 电子课本下载工具 v1.3
# 作者：肥宅水水呀（https://space.bilibili.com/324042405）
#       wuziqian211（https://space.bilibili.com/425503913）

# 导入相关库
from functools import partial
import requests
import os
import platform
import json
import pyperclip
import sys

from PySide6.QtCore import (
    QCoreApplication,
    QMetaObject,
    QObject,
    QRunnable,
    QThreadPool,
    Signal,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QIcon,
    QFont,
)
from PySide6.QtWidgets import (
    QComboBox,
    QProgressBar,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QApplication,
    QMainWindow,
    QMessageBox,
    QFileDialog,
)

# 获取操作系统类型
os_name = platform.system()
bookList = None


# 解析URL
def parse(url):
    try:
        # 简单提取URL中的contentId（这种方法不严谨，但为了减少导入的库只能这样了）
        for q in url[url.find("?") + 1 :].split("&"):
            if q.split("=")[0] == "contentId":
                contentId = q.split("=")[1]
                break

        response = requests.get(
            f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{contentId}.json"
        )
        data = json.loads(response.text)
        for item in list(data["ti_items"]):
            if item["lc_ti_format"] == "pdf":  # 找到存有PDF链接列表的项
                pdf_url = item["ti_storages"][0].replace("-private", "")  # 获取并构建PDF的URL
                break

        return pdf_url, contentId
    except:
        return None, None  # 如果解析失败，返回None


# 获取默认文件名
def getDefaultFilename(contentId):
    response = requests.get(
        f"https://s-file-1.ykt.cbern.com.cn/zxx/ndrv2/resources/tch_material/details/{contentId}.json"
    )
    try:
        data = json.loads(response.text)
        return data["title"]  # 返回教材标题
    except:
        return None


class DownloadSignalEmitter(QObject):
    size = Signal(int)
    progress = Signal(int)
    finished = Signal(str)


class DownloadWorker(QRunnable):
    def __init__(self, wnd, url, save_path):
        super().__init__()
        self.wnd = wnd
        self.url = url
        self.save_path = save_path
        self.emitter = DownloadSignalEmitter()

    def run(self):
        response = requests.get(self.url, stream=True)
        total_size = int(response.headers.get("Content-Length", 0))
        self.emitter.size.emit(total_size)
        with open(self.save_path, "wb") as file:
            downloaded = 0
            for chunk in response.iter_content(chunk_size=131072):  # 分块下载
                file.write(chunk)
                downloaded += len(chunk)
                self.emitter.progress.emit(downloaded)
        self.emitter.finished.emit(self.save_path)


def showFinishMsg(wnd, save_path):
    QMessageBox.information(wnd, "完成", f"文件已下载到：{save_path}")  # 显示完成对话框


# 解析并复制链接的函数
def parseAndCopy(wnd, text):
    urls = [line.strip() for line in text.splitlines() if line.strip()]  # 获取所有非空行
    pdf_links = []
    failed_links = []

    for url in urls:
        pdf_url = parse(url)[0]
        if not pdf_url:
            failed_links.append(url)  # 添加到失败链接
            continue
        pdf_links.append(pdf_url)

    if failed_links:
        failed_msg = "以下链接无法解析：\n" + "\n".join(failed_links)
        QMessageBox.information(wnd, "警告", failed_msg)  # 显示警告对话框
    if pdf_links:
        pyperclip.copy("\n".join(pdf_links))  # 将链接复制到剪贴板
        QMessageBox.information(wnd, "提示", "PDF链接已复制到剪贴板")


class BookHelper:
    def __init__(self):
        self.parsedHierarchy = None

    # 解析层级数据
    def parse_hierarchy(self, hier):
        parsed = {}

        # 如果没有层级数据，返回空
        if not hier:
            return None
        for h in hier:
            for ch in h["children"]:
                parsed[ch["tag_id"]] = {
                    "name": ch["tag_name"],
                    "children": self.parse_hierarchy(ch["hierarchies"]),
                }
        return parsed

    # 获取课本列表
    def fetch_book_list(self):
        # 获取层级数据
        tagsResp = requests.get(
            "https://s-file-1.ykt.cbern.com.cn/zxx/ndrs/tags/tch_material_tag.json"
        )
        tagsData = tagsResp.json()
        self.parsedHierarchy = self.parse_hierarchy(tagsData["hierarchies"])

        # 获取课本列表 URL 列表
        listResp = requests.get(
            "https://s-file-2.ykt.cbern.com.cn/zxx/ndrs/resources/tch_material/version/data_version.json"
        )
        listData = listResp.json()["urls"].split(",")

        # 获取课本列表
        for url in listData:
            bookResp = requests.get(url)
            bookData = bookResp.json()
            for i in bookData:
                # 解析课本层级数据
                tagPaths = i["tag_paths"][0].split("/")[2:]

                # 如果课本层级数据不在层级数据中，跳过
                tempHier = self.parsedHierarchy[i["tag_paths"][0].split("/")[1]]
                if not tagPaths[0] in tempHier["children"]:
                    continue

                # 分别解析课本层级
                for p in tagPaths:
                    if tempHier["children"] and tempHier["children"].get(p):
                        tempHier = tempHier["children"].get(p)
                if not tempHier["children"]:
                    tempHier["children"] = {}
                tempHier["children"][i["id"]] = i

        return self.parsedHierarchy


class Ui_MainWindow:
    eventFlag = False

    def __init__(self):
        self.threadPool = None

    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName("MainWindow")
        MainWindow.resize(600, 550)
        self.mainWidget = QWidget(MainWindow)
        self.mainWidget.setObjectName("mainWidget")
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setSpacing(20)
        self.verticalLayout.setObjectName("verticalLayout")
        self.mainWidget.setLayout(self.verticalLayout)

        self.topSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.verticalLayout.addItem(self.topSpacer)

        self.title = QLabel(self.mainWidget)
        self.title.setObjectName("title")
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self.title.setFont(font)
        self.title.setWordWrap(False)

        self.verticalLayout.addWidget(self.title, 0, Qt.AlignHCenter)

        self.helpDesc = QLabel(self.mainWidget)
        self.helpDesc.setObjectName("helpDesc")

        self.verticalLayout.addWidget(self.helpDesc, 0, Qt.AlignHCenter)

        self.menuParentLayout = QHBoxLayout()
        self.menuParentLayout.setObjectName("menuParentLayout")
        self.menuLeftSpacer = QSpacerItem(
            40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum
        )

        self.menuParentLayout.addItem(self.menuLeftSpacer)

        self.menuVerticalLayout = QVBoxLayout()
        self.menuVerticalLayout.setObjectName("menuVerticalLayout")

        self.menuRow1 = QHBoxLayout()
        self.menuRow1.setObjectName("menuRow1")
        self.menuRow1.setSpacing(24)

        self.menuVerticalLayout.addLayout(self.menuRow1)

        self.comboBox_1 = QComboBox(self.mainWidget)
        self.comboBox_1.setObjectName("comboBox_1")
        self.comboBox_1.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.menuRow1.addWidget(self.comboBox_1)

        self.comboBox_2 = QComboBox(self.mainWidget)
        self.comboBox_2.setObjectName("comboBox_2")
        self.comboBox_2.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.menuRow1.addWidget(self.comboBox_2)

        self.comboBox_3 = QComboBox(self.mainWidget)
        self.comboBox_3.setObjectName("comboBox_3")
        self.comboBox_3.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.menuRow1.addWidget(self.comboBox_3)

        self.comboBox_4 = QComboBox(self.mainWidget)
        self.comboBox_4.setObjectName("comboBox_4")
        self.comboBox_4.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.menuRow1.addWidget(self.comboBox_4)

        self.menuRow2 = QHBoxLayout()
        self.menuRow2.setObjectName("menuRow2")
        self.menuRow2.setSpacing(24)

        self.menuVerticalLayout.addLayout(self.menuRow2)

        self.comboBox_5 = QComboBox(self.mainWidget)
        self.comboBox_5.setObjectName("comboBox_5")
        self.comboBox_5.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.menuRow2.addWidget(self.comboBox_5)

        self.comboBox_6 = QComboBox(self.mainWidget)
        self.comboBox_6.setObjectName("comboBox_6")
        self.comboBox_6.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.menuRow2.addWidget(self.comboBox_6)

        self.menuParentLayout.addLayout(self.menuVerticalLayout)

        self.menuRightSpacer = QSpacerItem(
            40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum
        )

        self.menuParentLayout.addItem(self.menuRightSpacer)

        self.verticalLayout.addLayout(self.menuParentLayout)

        self.textLayout = QHBoxLayout()
        self.textLayout.setObjectName("textLayout")
        self.textLeftSpacer = QSpacerItem(
            40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum
        )

        self.textLayout.addItem(self.textLeftSpacer)

        self.textEdit = QTextEdit(self.mainWidget)
        self.textEdit.setObjectName("textEdit")
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.textEdit.setSizePolicy(sizePolicy)
        self.textEdit.setMinimumSize(QSize(400, 0))

        self.textLayout.addWidget(self.textEdit)

        self.textRightSpacer = QSpacerItem(
            40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum
        )

        self.textLayout.addItem(self.textRightSpacer)

        self.verticalLayout.addLayout(self.textLayout)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setSpacing(12)
        self.buttonLayout.setObjectName("buttonLayout")
        self.buttonLayout.setContentsMargins(48, -1, 48, -1)

        self.btnLeftSpacer = QSpacerItem(
            40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        self.buttonLayout.addItem(self.btnLeftSpacer)

        self.downloadBtn = QPushButton(self.mainWidget)
        self.downloadBtn.setObjectName("downloadBtn")
        self.downloadBtn.setSizePolicy(sizePolicy)
        self.downloadBtn.setMinimumSize(QSize(0, 40))

        self.buttonLayout.addWidget(self.downloadBtn)

        self.downloadLayout = QVBoxLayout()
        self.downloadLayout.setObjectName("downloadLayout")
        self.downloadLayout.setSpacing(8)
        self.downloadLayout.setContentsMargins(12, -1, 12, -1)

        self.downloadProgress = QLabel(self.mainWidget)
        self.downloadProgress.setObjectName("downloadProgress")
        self.downloadProgress.setAlignment(Qt.AlignCenter)

        self.downloadLayout.addWidget(self.downloadProgress)

        self.downloadProgressBar = QProgressBar(self.mainWidget)
        self.downloadProgressBar.setObjectName("downloadProgressBar")
        self.downloadProgressBar.setValue(0)
        self.downloadProgressBar.setAlignment(Qt.AlignCenter)
        self.downloadProgressBar.setMinimumSize(QSize(150, 30))

        self.downloadLayout.addWidget(self.downloadProgressBar)

        self.buttonLayout.addLayout(self.downloadLayout)

        self.copyBtn = QPushButton(self.mainWidget)
        self.copyBtn.setObjectName("copyBtn")
        self.copyBtn.setSizePolicy(sizePolicy)
        self.copyBtn.setMinimumSize(QSize(0, 40))

        self.buttonLayout.addWidget(self.copyBtn)

        self.btnRightSpacer = QSpacerItem(
            40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum
        )
        self.buttonLayout.addItem(self.btnRightSpacer)

        self.verticalLayout.addLayout(self.buttonLayout)

        self.bottomSpacer = QSpacerItem(
            20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding
        )

        self.verticalLayout.addItem(self.bottomSpacer)

        MainWindow.setCentralWidget(self.mainWidget)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.comboBoxes = [
            self.comboBox_1,
            self.comboBox_2,
            self.comboBox_3,
            self.comboBox_4,
            self.comboBox_5,
            self.comboBox_6,
        ]

        self.comboBox_1.currentTextChanged.connect(partial(self.TrySelEvent, 0))
        self.comboBox_2.currentTextChanged.connect(partial(self.TrySelEvent, 1))
        self.comboBox_3.currentTextChanged.connect(partial(self.TrySelEvent, 2))
        self.comboBox_4.currentTextChanged.connect(partial(self.TrySelEvent, 3))
        self.comboBox_5.currentTextChanged.connect(partial(self.TrySelEvent, 4))
        self.comboBox_6.currentTextChanged.connect(partial(self.TrySelEvent, 5))

        self.downloadBtn.clicked.connect(
            lambda: self.download(MainWindow, self.textEdit.toPlainText())
        )
        self.copyBtn.clicked.connect(
            lambda: parseAndCopy(MainWindow, self.textEdit.toPlainText())
        )

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(
            QCoreApplication.translate("MainWindow", "国家中小学智慧教育平台 电子课本解析", None)
        )
        self.title.setText(
            QCoreApplication.translate(
                "MainWindow",
                "国家中小学智慧教育平台 电子课本解析",
                None,
            )
        )
        self.helpDesc.setText(
            QCoreApplication.translate(
                "MainWindow",
                """请在下面的文本框中粘贴一个或多个课本原网址（支持批量每个URL一行）。
例如:
https://basic.smartedu.cn/tchMaterial/detail?contentType=
assets_document&contentId=b8e9a3fe-dae7-49c0-86cb-d146
f883fd8e&catalogType=tchMaterial&subCatalog=tchMaterial
点击下载按钮后，程序会解析并下载所有PDF文件。""",
                None,
            )
        )
        self.downloadBtn.setText(QCoreApplication.translate("MainWindow", "下载", None))
        self.copyBtn.setText(QCoreApplication.translate("MainWindow", "解析并复制", None))

        for i in ["---"] + [bookList[k]["name"] for k in bookList.keys()]:
            self.comboBox_1.addItem(i)

        self.downloadProgress.setText(
            QCoreApplication.translate(
                "MainWindow",
                "等待下载",
                None,
            )
        )

    def TrySelEvent(self, index, event):
        try:
            self.SelEvent(index, event)
        except:
            pass

    def SelEvent(self, index, event):
        # 重置后面的选择项
        if self.comboBoxes[index].currentText() == "---":
            for i in range(index + 1, len(self.comboBoxes)):
                self.comboBoxes[i].clear()
                self.comboBoxes[i].addItem("---")

                self.eventFlag = True
                self.comboBoxes[i].setCurrentIndex(0)
            return

        # 更新选择项
        if index < len(self.comboBoxes) - 1:
            currP1 = self.comboBoxes[index + 1]

            currHier = bookList
            currID = [
                element
                for element in currHier
                if currHier[element]["name"] == self.comboBoxes[0].currentText()
            ][0]
            currHier = currHier[currID]["children"]

            endFlag = False  # 是否到达最终目标
            for i in range(index):
                try:
                    currID = [
                        element
                        for element in currHier
                        if currHier[element]["name"]
                        == self.comboBoxes[i + 1].currentText()
                    ][0]
                    currHier = currHier[currID]["children"]
                except KeyError:  # 无法继续向下选择，说明已经到达最终目标
                    endFlag = True

            if endFlag:
                currOptions = ["---"]
            if not "name" in currHier[list(currHier.keys())[0]]:
                currOptions = ["---"] + [currHier[k]["title"] for k in currHier.keys()]
            else:
                currOptions = ["---"] + [currHier[k]["name"] for k in currHier.keys()]

            currP1.clear()
            for choice in currOptions:
                currP1.addItem(choice)

            # 到达目标，显示 URL
            if endFlag:
                currID = [
                    element
                    for element in currHier
                    if currHier[element]["title"]
                    == self.comboBoxes[index].currentText()
                ][0]

                if self.textEdit.toPlainText() == "":
                    self.textEdit.insertPlainText(
                        f"https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial"
                    )
                else:
                    self.textEdit.insertPlainText(
                        f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial"
                    )

                self.comboBoxes[-1].clear()
                self.comboBoxes[-1].addItem("---")

                self.eventFlag = True
                self.comboBoxes[-1].setCurrentIndex(0)
                return

            # 重置后面的选择项
            for i in range(index + 2, len(self.comboBoxes)):
                self.comboBoxes[i].clear()
                self.comboBoxes[i].addItem("---")
                # drops[i]["menu"].configure(state="disabled")

            for i in range(index + 1, len(self.comboBoxes)):
                self.eventFlag = True
                self.comboBoxes[i].setCurrentIndex(0)

        else:  # 最后一项，必为最终目标，显示 URL
            if self.comboBoxes[index].currentText() == "---":
                return

            currHier = bookList
            currID = [
                element
                for element in currHier
                if currHier[element]["name"] == self.comboBoxes[0].currentText()
            ][0]
            currHier = currHier[currID]["children"]
            for i in range(index - 1):
                currID = [
                    element
                    for element in currHier
                    if currHier[element]["name"] == self.comboBoxes[i + 1].currentText()
                ][0]
                currHier = currHier[currID]["children"]

            currID = [
                element
                for element in currHier
                if currHier[element]["title"] == self.comboBoxes[index].currentText()
            ][0]
            if self.textEdit.toPlainText() == "":
                self.textEdit.insertPlainText(
                    f"https://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial"
                )
            else:
                self.textEdit.insertPlainText(
                    f"\nhttps://basic.smartedu.cn/tchMaterial/detail?contentType=assets_document&contentId={currID}&catalogType=tchMaterial&subCatalog=tchMaterial"
                )

    # 下载PDF文件的函数
    def download(self, wnd, text):
        urls = [line.strip() for line in text.splitlines() if line.strip()]  # 获取所有非空行
        failed_links = []

        if len(urls) > 1:
            QMessageBox.information(wnd, "提示", "您选择了多个链接，将在选定的文件夹中使用教材名称作为文件名进行下载。")
            dir_path = QFileDialog.getExistingDirectory(wnd, "选择文件夹")  # 选择文件夹
            if os_name == "Windows":
                dir_path = dir_path.replace("/", "\\")
            if not dir_path:
                return
        else:
            dir_path = None

        for url in urls:
            pdf_url, contentId = parse(url)
            if not pdf_url:
                failed_links.append(url)  # 添加到失败链接
                continue

            if dir_path:
                default_filename = getDefaultFilename(contentId) or "download"
                save_path = os.path.join(dir_path, f"{default_filename}.pdf")  # 构造完整路径
            else:
                default_filename = getDefaultFilename(contentId) or "download"
                save_path, _ = QFileDialog.getSaveFileName(
                    wnd,
                    "保存文件",
                    os.path.join(os.getcwd(), default_filename),
                    "PDF files (*.pdf);;All files (*.*)",
                )  # 选择保存路径
                if os_name == "Windows":
                    save_path = save_path.replace("/", "\\")

                if not save_path:
                    return

            if not self.threadPool:
                self.threadPool = QThreadPool()

            self.downloadBtn.setEnabled(False)

            worker = DownloadWorker(wnd, pdf_url, save_path)
            worker.emitter.size.connect(self.downloadProgressBar.setMaximum)
            worker.emitter.progress.connect(self.downloadProgressBar.setValue)
            worker.emitter.progress.connect(
                lambda value: self.downloadProgress.setText(
                    f"{value / 1024 / 1024:.2f}MB / {self.downloadProgressBar.maximum() / 1024 / 1024:.2f}MB"
                )
            )
            worker.emitter.finished.connect(partial(showFinishMsg, wnd))
            worker.emitter.finished.connect(
                lambda _: self.downloadProgress.setText(f"等待下载")
            )
            worker.emitter.finished.connect(
                lambda _: self.downloadProgressBar.setValue(0)
            )
            worker.emitter.finished.connect(lambda _: self.downloadBtn.setEnabled(True))
            self.threadPool.start(worker)

        if failed_links:
            failed_msg = "以下链接无法解析：\n" + "\n".join(failed_links)
            QMessageBox.information(wnd, "警告", failed_msg)  # 显示警告对话框


# GUI
app = QApplication(sys.argv)

icon = QIcon("favicon.ico")
app.setWindowIcon(icon)

MainWindow = QMainWindow()

try:
    bookList = BookHelper().fetch_book_list()
except:
    QMessageBox.warning(MainWindow, "网络连接异常，程序将关闭。", "警告")  # 弹出警告窗口
    sys.exit()  # 退出自身进程

Ui_MainWindow().setupUi(MainWindow)

MainWindow.show()

sys.exit(app.exec())
