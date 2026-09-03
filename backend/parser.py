import re
from html.parser import HTMLParser


class SigaaPage(HTMLParser):
    """Extrai os campos dos formulários e resultados usados pelo planejador."""

    def __init__(self, html):
        super().__init__()
        self.inputs = {}
        self.units = []
        self.rows = []
        self.select = None
        self.option = None
        self.table = False
        self.row = None
        self.cell = None
        self.subject = ""
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name"):
            self.inputs[attributes["name"]] = attributes.get("value", "")
        if tag == "select":
            self.select = attributes.get("name")
        if tag == "option" and self.select == "form:selectUnidade":
            self.option = [attributes.get("value", ""), ""]
        if tag == "table" and attributes.get("id") == "lista-turmas":
            self.table = True
        if self.table and tag == "tr":
            self.row = {"class": attributes.get("class", ""), "cells": []}
        if self.row is not None and tag in ("td", "th"):
            self.cell = ""

    def handle_data(self, data):
        if self.option is not None:
            self.option[1] += data
        if self.cell is not None:
            self.cell += " " + data

    def handle_endtag(self, tag):
        if tag == "option" and self.option is not None:
            self.units.append(
                {"value": self.option[0], "label": self.option[1].strip()}
            )
            self.option = None
        if tag == "select":
            self.select = None
        if tag in ("td", "th") and self.cell is not None:
            self.row["cells"].append(" ".join(self.cell.split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            cells = self.row["cells"]
            if "destaque" in self.row["class"] and cells:
                self.subject = cells[0]
            elif len(cells) >= 9 and re.fullmatch(r"\d{4}\.\d", cells[0]):
                self.rows.append(
                    dict(
                        zip(
                            [
                                "disciplina",
                                "periodo",
                                "turma",
                                "docente",
                                "tipo",
                                "forma",
                                "situacao",
                                "horario",
                                "local",
                                "vagas",
                            ],
                            [self.subject] + cells[:9],
                        )
                    )
                )
            self.row = None
        if tag == "table":
            self.table = False
