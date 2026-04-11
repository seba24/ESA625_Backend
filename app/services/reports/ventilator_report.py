# -*- coding: utf-8 -*-
"""
Generador de Reportes PDF para Ventiladores
Genera reportes profesionales de pruebas de ventiladores TSI/Fluke

Hereda de BaseReportGenerator para mantener formato consistente con otros módulos.

Incluye:
- Primera página estandarizada (cliente, equipo, resumen, firmas)
- Secciones por configuración de pulmón (C, R, Vt teórico)
- Tabla detallada de parámetros con referencia, medido, error, tolerancia
- Compatibilidad con formato plano (sin lung configs) como fallback
- Conclusiones automáticas según ISO 80601-2-12
"""

import io
import os
import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging

from app.services.reports.base_report_generator import BaseReportGenerator

log = logging.getLogger(__name__)


class VentilatorReportGenerator(BaseReportGenerator):
    """
    Generador de reportes PDF para pruebas de ventiladores.

    Hereda de BaseReportGenerator para mantener formato consistente.
    La primera página tiene el mismo formato que los demás módulos.
    """

    MODULE_NAME = "VENTILADOR"
    MODULE_TITLE = "VALIDACIÓN TRAZABLE — VENTILADOR"
    MODULE_SUBTITLE = "Analizador de Ventilación Mecánica"
    MODULE_STANDARD = "ISO 80601-2-12"

    def __init__(self):
        super().__init__()

    def generate_report(self,
                        results_data: Dict[str, Any],
                        output_path: Optional[str] = None) -> Optional[str]:
        """
        Generar reporte PDF de resultados de ventilador.

        Args:
            results_data: Diccionario con datos del reporte:
                - results: dict con overall_status, measurements list,
                           lung_config_results list, etc.
                - client: dict con datos del cliente
                - equipment: dict con datos del equipo
                - protocol: dict con datos del protocolo
                - analyzer: dict con modelo y serie del analizador
            output_path: Ruta de salida opcional.

        Returns:
            Ruta del archivo generado o None si hay error
        """
        try:
            from reportlab.platypus import PageBreak, Spacer
        except ImportError as e:
            log.error(f"Dependencia no instalada: {e}")
            return None

        self._init_colors_and_styles()
        self.elements = []

        if not results_data:
            log.error("results_data es None o vacío")
            return None

        results = results_data.get('results', {}) or {}
        client_info = results_data.get('client', {}) or {}
        equipment_info = results_data.get('equipment', {}) or {}
        protocol_info = results_data.get('protocol', {}) or {}
        analyzer_info = results_data.get('analyzer', {}) or {}

        # Configurar logo y empresa desde el protocolo (fallback si no se seteo desde afuera)
        if isinstance(protocol_info, dict):
            if not self.company_name and protocol_info.get('company_name'):
                self.company_name = protocol_info['company_name']
            if not self.logo_path and protocol_info.get('logo_path'):
                logo = protocol_info['logo_path']
                if os.path.exists(logo):
                    self.logo_path = logo

        # Obtener datos de mediciones
        measurements = results.get('measurements', [])
        lung_config_results = results.get('lung_config_results', [])

        # Calcular contadores
        passed = sum(1 for m in measurements if m.get('passed', False))
        failed = sum(1 for m in measurements if not m.get('passed', True))
        total = len(measurements)
        test_passed = (failed == 0 and passed > 0)

        overall_status = results.get('overall_status', 'PASS' if test_passed else 'FAIL')
        protocol_name = protocol_info.get('name', 'Protocolo de Ventilador')

        # Actualizar subtítulo con modelo de analizador
        analyzer_model = analyzer_info.get('model', '')
        if analyzer_model:
            self.MODULE_SUBTITLE = f"Analizador {analyzer_model}"

        # ========== PRIMERA PÁGINA ==========

        self._add_title_section(protocol_name, test_passed)
        self._add_client_section(client_info)

        # Datos del equipo (ventilador bajo prueba)
        self._add_equipment_section(equipment_info, "DATOS DEL EQUIPO BAJO PRUEBA (VENTILADOR)")

        # Info adicional específica de ventilador
        extra_info = []
        ventilator_manufacturer = equipment_info.get('ventilator_manufacturer', '') or equipment_info.get('marca', '')
        ventilator_model = equipment_info.get('ventilator_model', '') or equipment_info.get('modelo', '')
        if ventilator_manufacturer:
            extra_info.append(("Fabricante Ventilador:", ventilator_manufacturer))
        if ventilator_model:
            extra_info.append(("Modelo Ventilador:", ventilator_model))

        # Info de configs de pulmón
        if lung_config_results:
            config_names = list(dict.fromkeys(
                lcr.get('config_name', '') for lcr in lung_config_results))
            extra_info.append(("Configuraciones:", ", ".join(config_names)))

        # Info multigas
        multigas_levels = results.get('multigas_levels', [])
        if results.get('multigas_enabled') and multigas_levels:
            levels_str = ", ".join(f"{gl:.0f}%" for gl in multigas_levels)
            extra_info.append(("Niveles O2:", levels_str))

        self._add_execution_info_section(
            start_time=results.get('start_time'),
            protocol_name=protocol_name,
            passed=passed,
            failed=failed,
            skipped=0,
            overall_status='pass' if test_passed else 'fail',
            extra_info=extra_info if extra_info else None
        )

        self._add_analyzer_section(analyzer_info, "ANALIZADOR UTILIZADO")

        self._add_signature_section()

        # Salto de página para resultados detallados
        self.elements.append(PageBreak())

        # ========== SEGUNDA PÁGINA+ ==========

        # Resultados: multigas, por config, o formato plano
        is_multigas = results.get('multigas_enabled', False)
        gas_level_results = results.get('gas_level_results', [])

        if is_multigas and gas_level_results:
            self._add_multigas_results(gas_level_results)
        elif lung_config_results:
            self._add_lung_config_results(lung_config_results)
        else:
            # Fallback: formato plano (compatibilidad)
            self._add_results_section(results)

        # Conclusiones
        conclusion_pass = (
            f"<b><font color='#10b981'>✓ EQUIPO APROBADO:</font></b> "
            f"El ventilador ha superado todas las pruebas de parámetros ventilatorios. "
            f"Todas las mediciones ({passed}) están dentro de la tolerancia especificada "
            f"según {self.MODULE_STANDARD}."
        )
        conclusion_fail = (
            f"<b><font color='#ef4444'>✗ EQUIPO NO APROBADO:</font></b> "
            f"El ventilador presenta {failed} mediciones fuera de tolerancia. "
            "Se requiere calibración o mantenimiento antes de su uso clínico. "
            "Las mediciones marcadas en rojo están fuera del rango permitido."
        )
        self._add_conclusion_section(passed, failed, 0, conclusion_pass, conclusion_fail)

        # Generar ruta de salida
        if not output_path:
            import tempfile
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            protocol_name_file = protocol_name.replace(' ', '_')
            output_path = os.path.join(tempfile.gettempdir(), f"Ventilador_{protocol_name_file}_{timestamp}.pdf")

        # Crear PDF
        buffer = io.BytesIO()
        doc = self._create_pdf_document(buffer)
        doc.build(self.elements)

        buffer.seek(0)
        pdf_bytes = self._add_page_numbers(buffer.getvalue())
        pdf_bytes = self._apply_pdf_security(pdf_bytes)
        pdf_bytes = self._sign_pdf(pdf_bytes)
        with open(output_path, 'wb') as f:
            f.write(pdf_bytes)

        log.info(f"Reporte PDF ventilador generado: {output_path}")
        return output_path

    def _add_lung_config_results(self, lung_config_results: List[Dict[str, Any]]):
        """
        Agregar secciones de resultados agrupados por configuración de pulmón.
        Cada config tiene: header con C, R, Vt teórico + tabla de resultados.
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors

        for lcr in lung_config_results:
            config_name = lcr.get('config_name', 'Sin nombre')
            compliance = lcr.get('compliance', 0)
            resistance = lcr.get('resistance', 0)
            csv_filename = lcr.get('csv_filename', '')
            selected_row = lcr.get('selected_row_index', 0)
            timestamp = lcr.get('selected_row_timestamp', '')
            theoretical_vt = lcr.get('theoretical_vt')
            config_results = lcr.get('results', [])

            # Header de configuración
            self.elements.append(Paragraph(
                f"CONFIGURACIÓN DE PULMÓN: {config_name.upper()}",
                self.style_seccion))

            # Tabla de info de la config
            vt_str = f"{theoretical_vt:.4f} L ({theoretical_vt*1000:.1f} mL)" if theoretical_vt else "N/A"
            info_data = [
                ["Compliance (C)", f"{compliance} mL/cmH2O",
                 "Resistance (R)", f"{resistance} cmH2O/L/s"],
                ["Vt Teórico", vt_str,
                 "Archivo CSV", csv_filename or "N/A"],
                ["Ciclo seleccionado", f"Fila {selected_row + 1}",
                 "Timestamp", timestamp or "N/A"],
            ]

            info_table = Table(info_data, colWidths=[110, 120, 110, 130], hAlign='LEFT')
            info_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), self.COLOR_GRIS_CLARO),
                ('BACKGROUND', (2, 0), (2, -1), self.COLOR_GRIS_CLARO),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            self.elements.append(info_table)
            self.elements.append(Spacer(1, 8))

            # Tabla de resultados
            if not config_results:
                self.elements.append(Paragraph(
                    "No hay mediciones registradas para esta configuración.",
                    self.styles['Normal']))
                self.elements.append(Spacer(1, 15))
                continue

            self._add_measurement_table(config_results)
            self.elements.append(Spacer(1, 15))

    def _add_multigas_results(self, gas_level_results: List[Dict[str, Any]]):
        """
        Agregar secciones de resultados agrupados por nivel de gas.
        Cada nivel tiene un header principal, y dentro las configs de pulmón.
        """
        from reportlab.platypus import Paragraph, Spacer, PageBreak
        from collections import OrderedDict

        # Agrupar por nivel de gas
        by_level: OrderedDict = OrderedDict()
        for glr in gas_level_results:
            gl = glr.get('gas_level_percent', 21)
            if gl not in by_level:
                by_level[gl] = []
            by_level[gl].append(glr.get('lung_config_result', {}))

        for gas_level, lcr_list in by_level.items():
            # Header de nivel de gas
            self.elements.append(Paragraph(
                f"NIVEL DE O2: {gas_level:.0f}%",
                self.style_titulo))
            self.elements.append(Spacer(1, 6))

            # Configs dentro de este nivel
            self._add_lung_config_results(lcr_list)
            self.elements.append(Spacer(1, 10))

    def _add_measurement_table(self, measurements: List[Dict[str, Any]]):
        """
        Agregar tabla de mediciones.
        Columnas: Parámetro | Referencia | Medido | Error% | Tolerancia | Estado
        """
        from reportlab.platypus import Table, TableStyle, Spacer
        from reportlab.lib import colors

        data = [["Parámetro", "Referencia", "Medido", "Error %", "Tolerancia", "Estado"]]

        table_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 3),
        ])

        row_index = 1

        for m in measurements:
            param_name = m.get('parameter', 'N/A')
            expected = m.get('expected', 0)
            measured = m.get('measured', 0)
            error = m.get('error', 0)
            tolerance = m.get('tolerance', m.get('max_error', 10))
            passed = m.get('passed', False)
            unit = m.get('unit', '')

            ref_str = f"{expected} {unit}".strip()
            meas_str = f"{measured:.2f} {unit}".strip() if isinstance(measured, (int, float)) else str(measured)
            error_str = f"{error:.1f}%" if isinstance(error, (int, float)) else str(error)
            tol_str = f"±{tolerance:.0f}%" if isinstance(tolerance, (int, float)) else str(tolerance)
            status_str = "APROBADO" if passed else "RECHAZADO"

            data.append([param_name, ref_str, meas_str, error_str, tol_str, status_str])

            if row_index % 2 == 0:
                table_style.add('BACKGROUND', (0, row_index), (-1, row_index), self.COLOR_GRIS_CLARO)

            if passed:
                table_style.add('TEXTCOLOR', (5, row_index), (5, row_index), self.COLOR_ACENTO)
                table_style.add('FONTNAME', (5, row_index), (5, row_index), 'Helvetica-Bold')
            else:
                table_style.add('BACKGROUND', (0, row_index), (-1, row_index), colors.HexColor('#fee2e2'))
                table_style.add('TEXTCOLOR', (0, row_index), (-1, row_index), self.COLOR_ERROR)
                table_style.add('FONTNAME', (0, row_index), (-1, row_index), 'Helvetica-Bold')

            row_index += 1

        tabla = Table(data, colWidths=[120, 75, 75, 60, 65, 75], hAlign='CENTER', repeatRows=1)
        tabla.setStyle(table_style)
        self.elements.append(tabla)

    def _add_results_section(self, results: Dict[str, Any]):
        """
        Fallback: Agregar tablas de resultados agrupados por categoría (formato plano).
        Se usa cuando no hay lung_config_results.
        """
        from reportlab.platypus import Paragraph, Spacer

        measurements = results.get('measurements', [])

        if not measurements:
            self.elements.append(Paragraph(
                "No hay mediciones registradas.", self.styles['Normal']))
            return

        try:
            from .protocols.models import VENTILATOR_PARAMETERS, PARAMETER_CATEGORIES
        except ImportError:
            VENTILATOR_PARAMETERS = {}
            PARAMETER_CATEGORIES = ['Flujo', 'Volumen', 'Presión', 'Temporización', 'Otros']

        # Agrupar mediciones por categoría
        categorized = {}

        for m in measurements:
            param_name = m.get('parameter', '')
            category = m.get('category', '')

            if not category:
                for pid, info in VENTILATOR_PARAMETERS.items():
                    if info.get('name') == param_name:
                        category = info.get('category', 'Otros')
                        break

            if not category:
                category = 'Otros'

            if category not in categorized:
                categorized[category] = []
            categorized[category].append(m)

        for cat in PARAMETER_CATEGORIES:
            if cat not in categorized:
                continue

            cat_measurements = categorized[cat]
            if not cat_measurements:
                continue

            self.elements.append(Paragraph(
                f"RESULTADOS - {cat.upper()}", self.style_seccion))
            self._add_measurement_table(cat_measurements)
            self.elements.append(Spacer(1, 10))

        for cat, cat_measurements in categorized.items():
            if cat not in PARAMETER_CATEGORIES and cat_measurements:
                self.elements.append(Paragraph(
                    f"RESULTADOS - {cat.upper()}", self.style_seccion))
                self._add_measurement_table(cat_measurements)
                self.elements.append(Spacer(1, 10))
