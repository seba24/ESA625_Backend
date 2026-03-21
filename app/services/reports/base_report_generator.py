# -*- coding: utf-8 -*-
"""
Clase Base para Generación de Reportes PDF

Define el formato estándar de primera página que deben seguir todos los módulos:
- Encabezado con título del módulo y logo
- Datos del cliente (mismo orden y posición siempre)
- Datos del equipo bajo prueba
- Información de ejecución (resumen)
- Sección de firmas

La segunda página en adelante contiene:
- Datos del analizador/instrumental
- Resultados detallados (específicos de cada módulo)
- Conclusiones

Este formato garantiza que el usuario siempre encuentre la información
en el mismo lugar, sin importar el tipo de prueba.

GUÍA PARA CREAR NUEVOS MÓDULOS (ECG Performance, Marcapasos, etc.):
========================================================================

1. Crear clase que herede de BaseReportGenerator:

   class ECGPerformanceReportGenerator(BaseReportGenerator):
       MODULE_TITLE = "PRUEBA DE ECG PERFORMANCE"
       MODULE_SUBTITLE = "Simulador de Paciente"
       MODULE_STANDARD = "IEC 60601-2-25"

       def __init__(self):
           super().__init__()
           # Atributos adicionales específicos del módulo

2. Implementar los métodos abstractos obligatorios:

   def _add_results_section(self, results: Dict[str, Any]):
       '''Tabla de resultados específica del módulo'''
       # Usar self.style_seccion, self.COLOR_*, etc.
       pass

   def generate_report(self, results_data: Dict[str, Any], output_path: Optional[str] = None) -> Optional[str]:
       '''Generar el reporte completo'''
       pass

3. En generate_report(), seguir esta estructura:

   # ======= PRIMERA PÁGINA (formato estándar) =======
   self._init_colors_and_styles()
   self.elements = []

   # 1. Título
   self._add_title_section(protocol_name, test_passed)

   # 2. Datos del cliente
   self._add_client_section(client_info)

   # 3. Datos del equipo
   self._add_equipment_section(equipment_info, "EQUIPO BAJO PRUEBA (MONITOR)")

   # 4. Información de la prueba
   self._add_execution_info_section(
       start_time=..., protocol_name=..., passed=..., failed=...,
       skipped=..., overall_status=..., extra_info=[("Campo extra:", valor)]
   )

   # 5. Analizador (en primera página)
   self._add_analyzer_section({'model': 'MPS450', 'serial': '...'})

   # 6. Firmas
   self._add_signature_section()

   # PageBreak
   from reportlab.platypus import PageBreak
   self.elements.append(PageBreak())

   # ======= SEGUNDA PÁGINA (resultados) =======

   # 7. Resultados específicos
   self._add_results_section(results)  # Tu implementación

   # 8. Conclusiones
   self._add_conclusion_section(passed, failed, skipped, conclusion_pass, conclusion_fail)

   # 9. Crear PDF
   buffer = io.BytesIO()
   doc = self._create_pdf_document(buffer)
   doc.build(self.elements)
   # ... guardar archivo

4. Campos de cliente disponibles (en orden estándar):
   - institucion/institution/name
   - pais/country
   - empresa/company
   - solicitante/contact/requester
   - direccion/address
   - cargo/position/title
   - ciudad/city
   - telefono/phone/tel
   - provincia/state/province
   - email/correo

5. Campos de equipo disponibles:
   - tipo_equipo/type/equipment_type
   - marca/manufacturer/brand
   - modelo/model
   - serie_equipo/serial/serial_number
   - inventario/inventory/asset_number
   - clase_equipo/class/equipment_class
   - tipo_partes_aplicadas/applied_parts_type
   - ubicacion/location

IMPORTANTE: Usar siempre los métodos de la clase base para mantener
consistencia visual en todos los reportes.
"""

import io
import os
import datetime
from typing import Dict, Any, List, Tuple, Optional
from abc import ABC, abstractmethod
import logging

log = logging.getLogger(__name__)


def add_pdf_page_numbers(pdf_bytes: bytes,
                         x: float = 490, y: float = 15,
                         font_name: str = "Helvetica",
                         font_size: float = 8,
                         color_hex: str = '#9ca3af') -> bytes:
    """
    Agregar numeración 'Pág. X de Y' a cada página de un PDF.

    Función compartida que usan tanto BaseReportGenerator como PDFExporter
    para garantizar formato de paginación consistente en todos los reportes.

    Args:
        pdf_bytes: Bytes del PDF sin numerar
        x: Posición horizontal del texto
        y: Posición vertical del texto
        font_name: Fuente a usar
        font_size: Tamaño de fuente
        color_hex: Color del texto en hexadecimal

    Returns:
        Bytes del PDF con numeración de páginas
    """
    try:
        from PyPDF2 import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.colors import HexColor

        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        total_pages = len(reader.pages)

        for page_number, page in enumerate(reader.pages, start=1):
            packet = io.BytesIO()
            can = pdf_canvas.Canvas(packet, pagesize=letter)

            can.setFillColor(HexColor(color_hex))
            can.setFont(font_name, font_size)
            can.drawString(x, y, f"Pág. {page_number} de {total_pages}")

            can.save()

            packet.seek(0)
            overlay = PdfReader(packet)
            page.merge_page(overlay.pages[0])
            writer.add_page(page)

        output = io.BytesIO()
        writer.write(output)
        result = output.getvalue()
        output.close()

        return result
    except Exception as e:
        log.warning(f"No se pudo agregar numeración de páginas: {e}")
        return pdf_bytes


class BaseReportGenerator(ABC):
    """
    Clase base abstracta para generadores de reportes PDF.

    Todos los módulos (Seguridad Eléctrica, Desfibrilador, ECG Performance,
    Marcapasos, etc.) deben heredar de esta clase para mantener consistencia.

    Estructura de primera página:
    1. Encabezado con barra azul y logo
    2. Título del reporte y resultado (APROBADO/NO APROBADO)
    3. DATOS DEL CLIENTE (tabla estandarizada)
    4. DATOS DEL EQUIPO BAJO PRUEBA
    5. INFORMACIÓN DE LA PRUEBA (resumen de ejecución)
    6. DATOS DEL INSTRUMENTAL (analizador)
    7. FIRMA DEL RESPONSABLE

    Segunda página en adelante:
    - Resultados específicos del módulo
    - Conclusiones
    """

    # Configuración del módulo - debe ser sobreescrita por subclases
    MODULE_TITLE = "REPORTE DE PRUEBA"
    MODULE_SUBTITLE = "Sistema ESA620"
    MODULE_STANDARD = "IEC 60601-1"

    def __init__(self):
        self._colors_initialized = False
        self.elements = []
        self.company_name: Optional[str] = None
        self.logo_path: Optional[str] = None
        self.technician_name: Optional[str] = None
        self.company_address: Optional[str] = None
        self.company_phone: Optional[str] = None
        self.company_email: Optional[str] = None
        self.company_website: Optional[str] = None
        self.company_accreditation: Optional[str] = None
        self.signature_image_path: Optional[str] = None
        self.company_logo_scale: int = 100  # Porcentaje de escala del logo (50-200%)
        self.company_logo_offset_x: int = 0  # Ajuste posición X del logo (puntos)
        self.company_logo_offset_y: int = 0  # Ajuste posición Y del logo (puntos)
        self._last_pdf_code: Optional[str] = None  # Código RPT-XXXXXX del último PDF generado

        # Cargar empresa y logo desde configuración global como valores base
        self._load_company_from_config()

    def _load_company_from_config(self):
        """Cargar nombre de empresa y logo desde la configuración global.
        En el backend, los datos vienen en results_data, no de config local."""
        try:
            config = {}  # Sin config local en backend

            if not self.company_name:
                self.company_name = config.get('company_name', '') or ''

            if not self.logo_path:
                logo = config.get('company_logo_path', '') or ''
                if logo and os.path.exists(logo):
                    self.logo_path = logo

            self.company_logo_scale = config.get('company_logo_scale', 100) or 100
            self.company_logo_offset_x = config.get('company_logo_offset_x', 0) or 0
            self.company_logo_offset_y = config.get('company_logo_offset_y', 0) or 0

            if not self.company_address:
                self.company_address = config.get('company_address', '') or ''
            if not self.company_phone:
                self.company_phone = config.get('company_phone', '') or ''
            if not self.company_email:
                self.company_email = config.get('company_email', '') or ''
            if not self.company_website:
                self.company_website = config.get('company_website', '') or ''
            if not self.company_accreditation:
                self.company_accreditation = config.get('company_accreditation', '') or ''
            if not self.technician_name:
                self.technician_name = config.get('technician_name', '') or ''
            if not self.signature_image_path:
                sig = config.get('signature_image_path', '') or ''
                if sig and os.path.exists(sig):
                    self.signature_image_path = sig
        except Exception:
            pass

    def _init_colors_and_styles(self):
        """Inicializar colores y estilos de ReportLab"""
        if self._colors_initialized:
            return

        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        # Paleta de colores profesional (consistente en todos los módulos)
        self.COLOR_PRIMARIO = colors.HexColor('#1e3a8a')       # Azul oscuro
        self.COLOR_SECUNDARIO = colors.HexColor('#3b82f6')     # Azul medio
        self.COLOR_ACENTO = colors.HexColor('#10b981')         # Verde éxito
        self.COLOR_ERROR = colors.HexColor('#ef4444')          # Rojo error
        self.COLOR_ADVERTENCIA = colors.HexColor('#f59e0b')    # Naranja
        self.COLOR_GRIS_CLARO = colors.HexColor('#f3f4f6')
        self.COLOR_GRIS_MEDIO = colors.HexColor('#9ca3af')

        self.styles = getSampleStyleSheet()
        self._create_custom_styles()
        self._colors_initialized = True

    def _create_custom_styles(self):
        """Crear estilos personalizados estandarizados"""
        from reportlab.lib.styles import ParagraphStyle

        # Título de empresa
        self.style_titulo = ParagraphStyle(
            name='TituloEmpresa',
            parent=self.styles['Normal'],
            fontSize=24,
            textColor=self.COLOR_PRIMARIO,
            spaceAfter=17,  # ~3mm separación del nombre a los datos de contacto
            alignment=1,  # CENTER
            fontName='Helvetica-Bold'
        )

        # Subtítulo
        self.style_subtitulo = ParagraphStyle(
            name='Subtitulo',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=self.COLOR_SECUNDARIO,
            spaceAfter=3,
            alignment=1,
            fontName='Helvetica-Bold'
        )

        # Subtítulo secundario
        self.style_subtitulo_secundario = ParagraphStyle(
            name='SubtituloSecundario',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=self.COLOR_GRIS_MEDIO,
            alignment=1,
            spaceAfter=3
        )

        # Sección con borde
        self.style_seccion = ParagraphStyle(
            name='Seccion',
            parent=self.styles['Heading2'],
            fontSize=11,
            textColor=self.COLOR_PRIMARIO,
            spaceAfter=4,
            spaceBefore=6,
            fontName='Helvetica-Bold',
            borderWidth=1,
            borderColor=self.COLOR_SECUNDARIO,
            borderPadding=3,
            backColor=self.COLOR_GRIS_CLARO,
            keepWithNext=1
        )

        # Info de protocolo
        self.style_protocol_info = ParagraphStyle(
            name='ProtocoloInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=self.COLOR_ACENTO,
            alignment=1,
            spaceAfter=2,
            fontName='Helvetica-Bold'
        )

        # Fecha
        self.style_fecha = ParagraphStyle(
            name='FechaGen',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=self.COLOR_GRIS_MEDIO,
            alignment=2,  # RIGHT
            spaceAfter=2
        )

        # Datos de contacto de empresa (centrado, gris, 8pt)
        self.style_company_detail = ParagraphStyle(
            name='CompanyDetail',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=self.COLOR_GRIS_MEDIO,
            alignment=1,  # CENTER
            spaceAfter=1
        )

        # Conclusiones
        self.style_conclusion = ParagraphStyle(
            name='Conclusion',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=10,
            spaceBefore=10,
            borderWidth=2,
            borderPadding=10,
            leftIndent=10,
            rightIndent=10
        )

        # Texto pequeño
        self.style_small = ParagraphStyle(
            name='SmallText',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=self.COLOR_GRIS_MEDIO,
        )

    def _create_header(self, canvas_obj, doc):
        """
        Crear encabezado de página (llamado en cada página).

        El encabezado incluye:
        - Barra azul con título del módulo
        - Subtítulo con norma aplicable
        - Logo (si está configurado)
        """
        from reportlab.lib import colors

        canvas_obj.saveState()

        # Barra de encabezado azul oscuro
        canvas_obj.setFillColor(self.COLOR_PRIMARIO)
        canvas_obj.rect(0, 730, 612, 62, fill=True, stroke=False)

        # Línea decorativa azul
        canvas_obj.setStrokeColor(self.COLOR_SECUNDARIO)
        canvas_obj.setLineWidth(3)
        canvas_obj.line(30, 725, 582, 725)

        # Título principal (blanco)
        canvas_obj.setFillColor(colors.white)
        canvas_obj.setFont("Helvetica-Bold", 16)
        canvas_obj.drawString(40, 755, self.MODULE_TITLE)

        # Subtítulo con norma
        canvas_obj.setFont("Helvetica", 10)
        canvas_obj.drawString(40, 740, f"{self.MODULE_SUBTITLE} - {self.MODULE_STANDARD}")

        # Logo si existe (escalado según company_logo_scale)
        if self.logo_path and os.path.exists(self.logo_path):
            try:
                scale = max(50, min(200, self.company_logo_scale)) / 100.0
                logo_w = 120 * scale
                logo_h = 50 * scale
                logo_x = 572 - logo_w + self.company_logo_offset_x
                logo_y = 735 + 50 - logo_h + self.company_logo_offset_y
                canvas_obj.drawImage(
                    self.logo_path, logo_x, logo_y,
                    width=logo_w, height=logo_h,
                    preserveAspectRatio=True,
                    mask='auto'
                )
            except Exception as e:
                log.warning(f"Error cargando logo: {e}")

        # Pie de página
        canvas_obj.setFillColor(self.COLOR_GRIS_CLARO)
        canvas_obj.rect(0, 0, 612, 30, fill=True, stroke=False)

        canvas_obj.setStrokeColor(self.COLOR_SECUNDARIO)
        canvas_obj.setLineWidth(2)
        canvas_obj.line(30, 35, 582, 35)

        canvas_obj.setFillColor(self.COLOR_GRIS_MEDIO)
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawString(40, 15, f"ESA620 - {self.MODULE_SUBTITLE}")
        canvas_obj.drawString(280, 15, f"Generado: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}")

        canvas_obj.restoreState()

    # =========================================================================
    # PRIMERA PÁGINA - Secciones estándar
    # =========================================================================

    def _add_title_section(self, protocol_name: str, test_passed: Optional[bool] = None):
        """
        Agregar sección de título del documento.

        Args:
            protocol_name: Nombre del protocolo utilizado
            test_passed: True si aprobó, False si no, None si no determinado
        """
        from reportlab.platypus import Paragraph, Spacer

        # Nombre de empresa
        if self.company_name:
            self.elements.append(Paragraph(self.company_name, self.style_titulo))

        # Datos de contacto de la empresa (compacto: max 2 líneas)
        # Línea 1: dirección + teléfono + email
        line1_parts = []
        if self.company_address:
            line1_parts.append(self.company_address)
        if self.company_phone:
            line1_parts.append(f"Tel: {self.company_phone}")
        if self.company_email:
            line1_parts.append(self.company_email)
        if line1_parts:
            self.elements.append(Paragraph(' | '.join(line1_parts), self.style_company_detail))
        # Línea 2: web + acreditación
        line2_parts = []
        if self.company_website:
            line2_parts.append(self.company_website)
        if self.company_accreditation:
            line2_parts.append(f"Acreditación: {self.company_accreditation}")
        if line2_parts:
            self.elements.append(Paragraph(' | '.join(line2_parts), self.style_company_detail))

        # Subtítulo con norma
        self.elements.append(Paragraph(
            f"Equipos Médicos - {self.MODULE_STANDARD}",
            self.style_subtitulo_secundario
        ))

        # Protocolo utilizado
        if protocol_name:
            self.elements.append(Paragraph(
                f"<b>Protocolo utilizado:</b> {protocol_name}",
                self.style_protocol_info
            ))

        # Resultado del test
        if test_passed is not None:
            if test_passed:
                result_text = "<font color='#10b981'><b>RESULTADO: APROBADO</b></font>"
            else:
                result_text = "<font color='#ef4444'><b>RESULTADO: NO APROBADO</b></font>"
            self.elements.append(Paragraph(result_text, self.style_protocol_info))

        # Fecha de generación
        fecha_actual = datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.elements.append(Paragraph(
            f"<i>Fecha de generación: {fecha_actual}</i>",
            self.style_fecha
        ))
        self.elements.append(Spacer(1, 5))

    def _add_client_section(self, client_info: Dict[str, Any]):
        """
        Agregar sección DATOS DEL CLIENTE con formato estándar.

        Orden de campos (siempre el mismo):
        1. Institución
        2. País
        3. Empresa
        4. Solicitante
        5. Dirección
        6. Cargo
        7. Ciudad
        8. Teléfono
        9. Provincia
        10. Email

        Args:
            client_info: Diccionario con datos del cliente
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer

        self.elements.append(Paragraph("DATOS DEL CLIENTE", self.style_seccion))

        if not client_info:
            self.elements.append(Spacer(1, 5))
            return

        # Construir lista de datos en orden estándar
        data = []

        # Mapeo de campos (pueden venir con diferentes nombres)
        field_mappings = [
            ("Institución:", ['institucion', 'institution', 'name']),
            ("País:", ['pais', 'country']),
            ("Empresa:", ['empresa', 'company']),
            ("Solicitante:", ['solicitante', 'contact', 'requester']),
            ("Dirección:", ['direccion', 'address']),
            ("Cargo:", ['cargo', 'position', 'title']),
            ("Ciudad:", ['ciudad', 'city']),
            ("Teléfono:", ['telefono', 'phone', 'tel']),
            ("Provincia:", ['provincia', 'state', 'province']),
            ("Email:", ['email', 'correo']),
        ]

        for label, keys in field_mappings:
            value = None
            for key in keys:
                if client_info.get(key):
                    value = client_info[key]
                    break
            if value:
                data.append([label, str(value)])

        if not data:
            self.elements.append(Spacer(1, 5))
            return

        # Siempre usar 4 columnas (2 pares label-valor) para formato compacto
        mid = (len(data) + 1) // 2
        datos_col1 = data[:mid]
        datos_col2 = data[mid:]

        datos_tabla = []
        for i in range(max(len(datos_col1), len(datos_col2))):
            fila = []
            if i < len(datos_col1):
                fila.extend(datos_col1[i])
            else:
                fila.extend(["", ""])
            if i < len(datos_col2):
                fila.extend(datos_col2[i])
            else:
                fila.extend(["", ""])
            datos_tabla.append(fila)

        tabla = Table(datos_tabla, colWidths=[100, 135, 100, 135], hAlign='CENTER')
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (2, 0), (2, -1), self.COLOR_PRIMARIO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        self.elements.append(tabla)
        self.elements.append(Spacer(1, 3))

    def _add_equipment_section(self, equipment_info: Dict[str, Any], title: str = "DATOS DEL EQUIPO BAJO PRUEBA"):
        """
        Agregar sección DATOS DEL EQUIPO con formato estándar.

        Orden de campos:
        1. Tipo de Equipo
        2. Marca/Fabricante
        3. Modelo
        4. Número de Serie
        5. Inventario
        6. Clase
        7. Tipo Partes Aplicadas
        8. Ubicación

        Args:
            equipment_info: Diccionario con datos del equipo
            title: Título de la sección (puede personalizarse por módulo)
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer

        self.elements.append(Paragraph(title, self.style_seccion))

        if not equipment_info:
            self.elements.append(Spacer(1, 5))
            return

        data = []

        # Mapeo de campos
        field_mappings = [
            ("Tipo de Equipo:", ['tipo_equipo', 'type', 'equipment_type']),
            ("Fabricante/Marca:", ['marca', 'manufacturer', 'brand']),
            ("Modelo:", ['modelo', 'model']),
            ("Número de Serie:", ['serie_equipo', 'serial', 'serial_number']),
            ("Inventario:", ['inventario', 'inventory', 'asset_number']),
            ("Clase:", ['clase_equipo', 'class', 'equipment_class']),
            ("Tipo Partes Aplicadas:", ['tipo_partes_aplicadas', 'applied_parts_type']),
            ("Ubicación:", ['ubicacion', 'location']),
        ]

        for label, keys in field_mappings:
            value = None
            for key in keys:
                if equipment_info.get(key):
                    value = equipment_info[key]
                    break
            if value:
                data.append([label, str(value)])

        if not data:
            self.elements.append(Spacer(1, 3))
            return

        # Usar 4 columnas (2 pares label-valor) para formato compacto
        mid = (len(data) + 1) // 2
        datos_col1 = data[:mid]
        datos_col2 = data[mid:]

        datos_tabla = []
        for i in range(max(len(datos_col1), len(datos_col2))):
            fila = []
            if i < len(datos_col1):
                fila.extend(datos_col1[i])
            else:
                fila.extend(["", ""])
            if i < len(datos_col2):
                fila.extend(datos_col2[i])
            else:
                fila.extend(["", ""])
            datos_tabla.append(fila)

        tabla = Table(datos_tabla, colWidths=[100, 135, 100, 135], hAlign='CENTER')
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (2, 0), (2, -1), self.COLOR_PRIMARIO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))

        self.elements.append(tabla)
        self.elements.append(Spacer(1, 3))

    def _add_execution_info_section(self,
                                     start_time: Optional[str] = None,
                                     protocol_name: str = "",
                                     passed: int = 0,
                                     failed: int = 0,
                                     skipped: int = 0,
                                     overall_status: str = "",
                                     extra_info: Optional[List[Tuple[str, str]]] = None):
        """
        Agregar sección INFORMACIÓN DE LA PRUEBA con formato estándar.

        Args:
            start_time: Fecha/hora de inicio (ISO format)
            protocol_name: Nombre del protocolo
            passed: Número de pruebas aprobadas
            failed: Número de pruebas rechazadas
            skipped: Número de pruebas omitidas
            overall_status: Estado general ('pass', 'fail', etc.)
            extra_info: Lista de tuplas (label, value) con info adicional
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer

        self.elements.append(Paragraph("INFORMACIÓN DE LA PRUEBA", self.style_seccion))

        data_rows = []

        # Fecha de ejecución
        if start_time:
            try:
                dt = datetime.datetime.fromisoformat(start_time)
                fecha_str = dt.strftime('%d/%m/%Y %H:%M:%S')
            except:
                fecha_str = start_time
        else:
            fecha_str = datetime.datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        data_rows.append(["Fecha de Ejecución:", fecha_str])

        # Protocolo
        if protocol_name:
            data_rows.append(["Protocolo:", protocol_name])

        # Info adicional específica del módulo
        if extra_info:
            for label, value in extra_info:
                data_rows.append([label, str(value)])

        # Resumen de resultados
        total = passed + failed + skipped
        data_rows.append(["Total de Pruebas:", str(total)])
        data_rows.append(["Pruebas Aprobadas:", str(passed)])
        data_rows.append(["Pruebas Rechazadas:", str(failed)])
        if skipped > 0:
            data_rows.append(["Pruebas Omitidas:", str(skipped)])

        # Estado general
        if overall_status:
            status_display = {
                'pass': 'APROBADO',
                'fail': 'NO APROBADO',
                'completed_successfully': 'APROBADO',
                'completed_with_failures': 'NO APROBADO',
                'cancelled': 'CANCELADO',
                'error': 'ERROR',
            }.get(overall_status.lower(), overall_status.upper())
            data_rows.append(["Resultado Final:", status_display])

        # Usar 4 columnas para formato compacto
        mid = (len(data_rows) + 1) // 2
        datos_col1 = data_rows[:mid]
        datos_col2 = data_rows[mid:]

        datos_tabla = []
        for i in range(max(len(datos_col1), len(datos_col2))):
            fila = []
            if i < len(datos_col1):
                fila.extend(datos_col1[i])
            else:
                fila.extend(["", ""])
            if i < len(datos_col2):
                fila.extend(datos_col2[i])
            else:
                fila.extend(["", ""])
            datos_tabla.append(fila)

        tabla = Table(datos_tabla, colWidths=[100, 135, 100, 135], hAlign='CENTER')
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLOR_PRIMARIO),
            ('TEXTCOLOR', (2, 0), (2, -1), self.COLOR_PRIMARIO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('BACKGROUND', (0, 0), (0, -1), self.COLOR_GRIS_CLARO),
            ('BACKGROUND', (2, 0), (2, -1), self.COLOR_GRIS_CLARO),
        ]))

        self.elements.append(tabla)
        self.elements.append(Spacer(1, 5))

    def _add_signature_section(self):
        """
        Agregar sección FIRMA DEL RESPONSABLE con formato estándar.

        Incluye espacio para:
        - Firma del técnico (imagen si disponible)
        - Firma del cliente/responsable
        """
        from reportlab.platypus import (
            Paragraph, Spacer, Table, TableStyle
        )

        self.elements.append(Spacer(1, 18))
        self.elements.append(
            Paragraph("FIRMA DEL RESPONSABLE", self.style_seccion)
        )

        technician = (
            self.technician_name
            if self.technician_name
            else "Nombre: __________________"
        )

        # Intentar cargar imagen de firma del técnico
        sig_cell = ""
        sig_row_height = 70
        if (self.signature_image_path
                and os.path.isfile(self.signature_image_path)):
            try:
                from reportlab.platypus import Image as RLImage
                sig_img = RLImage(self.signature_image_path)
                # Escalar proporcionalmente: max 150 ancho, 50 alto
                iw, ih = sig_img.drawWidth, sig_img.drawHeight
                max_w, max_h = 150, 50
                scale = min(max_w / iw, max_h / ih, 1.0)
                sig_img.drawWidth = iw * scale
                sig_img.drawHeight = ih * scale
                sig_cell = sig_img
                sig_row_height = max(sig_img.drawHeight + 10, 50)
            except Exception:
                sig_cell = ""

        data = [
            [sig_cell, ""],
            ["_" * 35, "_" * 35],
            ["Firma del Técnico",
             "Firma del Cliente/Responsable"],
            [technician, "Nombre: __________________"],
            ["Fecha: ___/___/______",
             "Fecha: ___/___/______"],
        ]

        tabla = Table(
            data,
            colWidths=[220, 220],
            rowHeights=[sig_row_height, None, None, None, None],
            hAlign='CENTER'
        )
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
            ('VALIGN', (0, 1), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 2), (-1, 2), 9),
        ]))

        self.elements.append(tabla)

        # Sello visual de firma digital
        self._add_visual_stamp()

    def _add_visual_stamp(self):
        """Agregar sello visual de firma digital si está configurado."""
        try:
            from ..common.config import get_config
            config = get_config()
        except Exception:
            return

        if not config.get('digital_signature_enabled', False):
            return
        if not config.get('digital_signature_show_stamp', True):
            return

        try:
            from .visual_stamp import VisualSignatureStamp
            from reportlab.platypus import Spacer

            signer = config.get('technician_name', '') or config.get('company_name', '')
            org = config.get('company_name', '')
            cert_cn = self._get_stamp_cert_cn(config)

            stamp = VisualSignatureStamp(
                signer_name=signer,
                organization=org,
                cert_cn=cert_cn,
                is_valid=True,
            )
            self.elements.append(Spacer(1, 10))
            self.elements.append(stamp)
        except ImportError:
            pass
        except Exception as e:
            log.warning(f"Error agregando sello visual: {e}")

    def _get_stamp_cert_cn(self, config) -> str:
        """Obtener CN del certificado para el sello visual."""
        try:
            method = config.get('digital_signature_method', 'file')
            if method == 'token':
                return config.get('token_cert_label', '')
            cert_path = config.get('digital_signature_cert_path', '')
            password = config.get('digital_signature_password', '')
            if cert_path:
                from .pdf_signer import PDFSigner
                info = PDFSigner.get_cert_info(cert_path, password)
                if info:
                    return info.get('common_name', '')
        except Exception:
            pass
        return ''

    # =========================================================================
    # SEGUNDA PÁGINA - Secciones comunes
    # =========================================================================

    def _add_analyzer_section(self, analyzer_info: Dict[str, Any], title: str = "DATOS DEL INSTRUMENTAL (ANALIZADOR)"):
        """
        Agregar sección DATOS DEL INSTRUMENTAL con formato estándar.

        Args:
            analyzer_info: Diccionario con datos del analizador
            title: Título de la sección
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer

        self.elements.append(Paragraph(title, self.style_seccion))

        data = []

        # Mapeo de campos
        field_mappings = [
            ("Modelo:", ['modelo', 'model', 'device_model']),
            ("Número de Serie:", ['serie', 'serial', 'device_serial']),
            ("Firmware UI:", ['firmware_ui']),
            ("Firmware Medidor:", ['firmware_meter']),
            ("Calibración:", ['calibracion', 'calibration']),
        ]

        for label, keys in field_mappings:
            value = None
            for key in keys:
                if analyzer_info.get(key):
                    value = analyzer_info[key]
                    break
            if value:
                data.append([label, str(value)])

        if not data:
            data.append(["Modelo:", "Ver panel trasero del equipo"])

        tabla = Table(data, colWidths=[150, 320], hAlign='LEFT')
        tabla.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLOR_SECUNDARIO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('BACKGROUND', (0, 0), (0, -1), self.COLOR_GRIS_CLARO),
        ]))

        self.elements.append(tabla)
        self.elements.append(Spacer(1, 5))

    def _add_calibration_info_section(self, analyzer_info: Dict[str, Any]):
        """
        Agregar sección de calibración del analizador en el PDF.

        Busca el registro de calibración más reciente para el analizador
        y muestra: Certificado, Fecha, Vencimiento, Laboratorio, Patrón, Incertidumbre.
        Si la calibración está vencida, muestra advertencia en rojo.
        """
        from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
        from reportlab.lib.colors import HexColor

        try:
            from sgc.components.client.calibration_storage import get_calibration_storage
            storage = get_calibration_storage()
        except Exception:
            return  # Si no hay storage disponible, no agregar sección

        # Buscar por nombre y serial del analizador
        analyzer_name = ""
        analyzer_serial = ""
        for key in ['modelo', 'model', 'device_model']:
            if analyzer_info.get(key):
                analyzer_name = str(analyzer_info[key])
                break
        for key in ['serie', 'serial', 'device_serial']:
            if analyzer_info.get(key):
                analyzer_serial = str(analyzer_info[key])
                break

        if not analyzer_name:
            return

        record = storage.get_latest_for_analyzer(analyzer_name, analyzer_serial)

        title = "CALIBRACIÓN DEL ANALIZADOR"
        self.elements.append(Paragraph(title, self.style_seccion))

        if not record:
            self.elements.append(Paragraph(
                "Sin registro de calibración",
                self._get_or_create_style('cal_no_data', parent='Normal',
                                          fontSize=9, textColor=HexColor('#6B7280'))
            ))
            self.elements.append(Spacer(1, 10))
            return

        data = [
            ["Certificado N°:", record.certificate_number or "—"],
            ["Fecha Calibración:", record.calibration_date or "—"],
            ["Próx. Vencimiento:", record.next_due_date or "—"],
            ["Laboratorio:", record.laboratory or "—"],
            ["Patrón/Referencia:", record.standard_reference or "—"],
            ["Incertidumbre:", f"±{record.uncertainty_percent}%" if record.uncertainty_percent else "—"],
        ]

        tabla = Table(data, colWidths=[150, 320], hAlign='LEFT')

        style_commands = [
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLOR_SECUNDARIO),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLOR_GRIS_MEDIO),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('BACKGROUND', (0, 0), (0, -1), self.COLOR_GRIS_CLARO),
        ]

        # Si calibración vencida, resaltar fila de vencimiento en rojo
        if record.is_expired:
            style_commands.append(
                ('TEXTCOLOR', (1, 2), (1, 2), HexColor('#DC2626'))
            )
            style_commands.append(
                ('FONTNAME', (1, 2), (1, 2), 'Helvetica-Bold')
            )

        tabla.setStyle(TableStyle(style_commands))
        self.elements.append(tabla)

        if record.is_expired:
            self.elements.append(Spacer(1, 3))
            self.elements.append(Paragraph(
                "⚠ CALIBRACIÓN VENCIDA",
                self._get_or_create_style('cal_expired', parent='Normal',
                                          fontSize=10, textColor=HexColor('#DC2626'),
                                          fontName='Helvetica-Bold')
            ))

        self.elements.append(Spacer(1, 15))

    def _get_or_create_style(self, name, parent='Normal', **kwargs):
        """Obtener o crear un ParagraphStyle."""
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        styles = getSampleStyleSheet()
        try:
            return styles[name]
        except KeyError:
            return ParagraphStyle(name, parent=styles[parent], **kwargs)

    def _add_conclusion_section(self, passed: int, failed: int, skipped: int = 0,
                                 conclusion_pass: str = "",
                                 conclusion_fail: str = ""):
        """
        Agregar sección CONCLUSIONES con formato estándar.

        Args:
            passed: Número de pruebas aprobadas
            failed: Número de pruebas rechazadas
            skipped: Número de pruebas omitidas
            conclusion_pass: Texto de conclusión si aprobó
            conclusion_fail: Texto de conclusión si no aprobó
        """
        from reportlab.platypus import Paragraph, Spacer

        self.elements.append(Paragraph("CONCLUSIONES", self.style_seccion))

        total = passed + failed + skipped

        if failed == 0 and passed > 0:
            if not conclusion_pass:
                conclusion_pass = (
                    f"<b><font color='#10b981'>✓ EQUIPO APROBADO:</font></b> "
                    f"El equipo ha superado todas las pruebas ({passed}). "
                    f"Los parámetros medidos cumplen con los requisitos de la norma {self.MODULE_STANDARD}."
                )
            conclusion_text = conclusion_pass
        else:
            if not conclusion_fail:
                conclusion_fail = (
                    f"<b><font color='#ef4444'>✗ EQUIPO NO APROBADO:</font></b> "
                    f"El equipo presenta {failed} pruebas fuera de especificación. "
                    f"Se requiere revisión o mantenimiento antes de su uso clínico."
                )
            conclusion_text = conclusion_fail

        self.elements.append(Paragraph(conclusion_text, self.style_conclusion))

        # Resumen estadístico
        resumen = f"""
        <b>Resumen estadístico:</b><br/>
        • Total de pruebas: {total}<br/>
        • Pruebas aprobadas: {passed}<br/>
        • Pruebas rechazadas: {failed}<br/>
        • Pruebas omitidas: {skipped}
        """
        self.elements.append(Paragraph(resumen, self.styles['Normal']))
        self.elements.append(Spacer(1, 15))

    # =========================================================================
    # Fotos del equipo (compartido por todos los módulos)
    # =========================================================================

    def _add_photos_section(self, photos, title="FOTOS DEL EQUIPO", max_photos=6):
        """
        Sección genérica de fotos en el PDF.

        Módulos con necesidades especiales (ECG con editor) pueden hacer override.

        Args:
            photos: Lista de dicts con 'path', 'description', opcional 'signal_code'
            title: Título de la sección
            max_photos: Máximo de fotos a incluir
        """
        from reportlab.platypus import Paragraph, Spacer, Image
        from reportlab.lib.units import inch

        if not photos:
            return

        valid_photos = [p for p in photos if os.path.exists(p.get('path', ''))]
        if not valid_photos:
            return

        self.elements.append(Paragraph(title, self.style_seccion))

        for photo in valid_photos[:max_photos]:
            description = photo.get('description', 'Sin descripcion')
            signal_code = photo.get('signal_code', '')
            display = f"{signal_code}: {description}" if signal_code and signal_code not in description else description

            self.elements.append(
                Paragraph(f"<i>{display}</i>", self.styles['Normal']))

            try:
                img = Image(photo['path'], width=4 * inch, height=3 * inch)
                img.hAlign = 'CENTER'
                self.elements.append(img)
                self.elements.append(Spacer(1, 10))
            except Exception:
                continue

        self.elements.append(Spacer(1, 15))

    # =========================================================================
    # Métodos abstractos - deben ser implementados por subclases
    # =========================================================================

    @abstractmethod
    def _add_results_section(self, results: Dict[str, Any]):
        """
        Agregar sección de resultados específica del módulo.

        Cada módulo implementa su propia tabla/formato de resultados.

        Args:
            results: Diccionario con resultados de las pruebas
        """
        pass

    @abstractmethod
    def generate_report(self, results_data: Dict[str, Any], output_path: Optional[str] = None) -> Optional[str]:
        """
        Generar el reporte PDF completo.

        Args:
            results_data: Datos completos del reporte
            output_path: Ruta de salida opcional

        Returns:
            Ruta del archivo generado o None si hay error
        """
        pass

    # =========================================================================
    # Utilidades
    # =========================================================================

    def _create_pdf_document(self, buffer: io.BytesIO):
        """
        Crear documento PDF base con plantilla estándar.

        Args:
            buffer: Buffer de bytes para escribir el PDF

        Returns:
            BaseDocTemplate configurado
        """
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate
        from reportlab.lib.units import inch

        doc = BaseDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=0.5*inch,
            rightMargin=0.5*inch,
            topMargin=1.12*inch,  # Espacio para encabezado (ajustado -2mm)
            bottomMargin=0.6*inch  # Espacio para pie
        )

        frame = Frame(
            doc.leftMargin,
            doc.bottomMargin,
            doc.width,
            doc.height,
            id='normal'
        )

        template = PageTemplate(id='main', frames=frame, onPage=self._create_header)
        doc.addPageTemplates([template])

        return doc

    def _add_page_numbers(self, pdf_bytes: bytes) -> bytes:
        """
        Agregar numeración 'Pág. X de Y' al pie de cada página del PDF.

        Delega a la función de módulo add_pdf_page_numbers() para mantener
        una implementación única compartida con PDFExporter.
        """
        return add_pdf_page_numbers(pdf_bytes)

    def _generate_pdf_unlock_code(self) -> Tuple[str, str]:
        """
        Generar código único y owner password para protección de PDF.

        Returns:
            (pdf_code, owner_password)
            - pdf_code: código visible para el usuario (ej: 'RPT-A3F7B2')
            - owner_password: password derivada, solo el desarrollador puede calcularla
        """
        import hashlib
        import secrets

        raw = secrets.token_hex(3).upper()  # 6 chars: A3F7B2
        pdf_code = f"RPT-{raw}"

        DEVELOPER_SALT = "ESA625_SR_CERT_2026"
        owner_password = hashlib.sha256(
            f"{pdf_code}:{DEVELOPER_SALT}".encode()
        ).hexdigest()[:16]

        return pdf_code, owner_password

    def _register_pdf_code(self, pdf_code: str, output_path: str):
        """
        Registrar código de PDF en el servidor (background, no bloquea).

        Args:
            pdf_code: Código único del PDF (ej: 'RPT-A3F7B2')
            output_path: Ruta del archivo PDF generado
        """
        import threading

        def _send():
            try:
                import json
                import urllib.request
                from ..common.constants import DEFAULT_WEBHOOK_URL
                from ..common.config import get_config

                config = get_config()
                machine_id = config.get('machine_id', 'unknown')
                hostname = os.environ.get('COMPUTERNAME', 'unknown')

                payload = json.dumps({
                    'action': 'register_pdf_code',
                    'pdf_code': pdf_code,
                    'machine_id': machine_id,
                    'hostname': hostname,
                    'filename': os.path.basename(output_path),
                    'timestamp': datetime.datetime.now().isoformat()
                }).encode('utf-8')

                req = urllib.request.Request(
                    DEFAULT_WEBHOOK_URL,
                    data=payload,
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                urllib.request.urlopen(req, timeout=10)
                log.debug(f"PDF code {pdf_code} registrado en servidor")
            except Exception as e:
                log.debug(f"No se pudo registrar PDF code en servidor: {e}")

        thread = threading.Thread(target=_send, daemon=True)
        thread.start()

    def _apply_pdf_security(self, pdf_bytes: bytes, output_path: str = '') -> bytes:
        """
        Aplicar seguridad al PDF si está configurado en las preferencias.

        Genera un código único RPT-XXXXXX por cada PDF y una owner_password
        derivada. El PDF se abre sin password (lectura libre) pero la edición,
        copia y anotación requieren la owner_password.

        La impresión queda habilitada en el PDF para que la app pueda imprimir
        filtrando impresoras virtuales.

        El código se guarda en self._last_pdf_code para mostrarlo al usuario.

        Args:
            pdf_bytes: Bytes del PDF sin encriptar
            output_path: Ruta del archivo (para registro en servidor)

        Returns:
            Bytes del PDF (encriptado si la opción está habilitada, sin cambios si no)
        """
        self._last_pdf_code = None

        try:
            from ..common.config import get_config
            config = get_config()
        except Exception:
            return pdf_bytes

        if not config.get('report_pdf_security', False):
            return pdf_bytes

        try:
            from PyPDF2 import PdfReader, PdfWriter

            # Generar código único y owner password
            pdf_code, owner_password = self._generate_pdf_unlock_code()

            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            # user_password="" permite abrir y leer sin contraseña
            # owner_password=única por PDF, protege edición/copia
            # permissions: lectura + impresión permitida, NO editar/copiar/anotar
            writer.encrypt(
                user_password="",
                owner_password=owner_password,
                permissions_flag=0b0000_0000_0100  # Solo lectura + print
            )

            output = io.BytesIO()
            writer.write(output)
            secured_bytes = output.getvalue()
            output.close()

            self._last_pdf_code = pdf_code
            log.info(f"PDF protegido con código {pdf_code} ({len(secured_bytes)} bytes)")

            # Registrar código en servidor (background)
            if output_path:
                self._register_pdf_code(pdf_code, output_path)

            return secured_bytes

        except ImportError:
            log.warning("PyPDF2 no disponible, PDF sin protección")
            return pdf_bytes
        except Exception as e:
            log.error(f"Error aplicando seguridad al PDF: {e}")
            return pdf_bytes

    def _sign_pdf(self, pdf_bytes: bytes) -> bytes:
        """
        Aplicar firma digital PKCS#7 al PDF si está configurado.

        Lee la configuración de digital_signature_enabled, digital_signature_cert_path
        y digital_signature_password del config. Si está habilitado y el certificado
        existe, firma el PDF con endesive.

        Args:
            pdf_bytes: Bytes del PDF (ya con page numbers y seguridad aplicados)

        Returns:
            Bytes del PDF firmado (o sin cambios si no está habilitado)
        """
        try:
            from ..common.config import get_config
            config = get_config()
        except Exception:
            return pdf_bytes

        if not config.get('digital_signature_enabled', False):
            return pdf_bytes

        method = config.get('digital_signature_method', 'file')
        location = config.get('company_address', '')
        contact = config.get('company_email', '')

        try:
            from .pdf_signer import PDFSigner

            if method == 'token':
                # Firma con token PKCS#11
                library = config.get('token_pkcs11_library', '')
                slot = int(config.get('token_slot', 0))
                pin = config.get('token_pin', '')
                cert_label = config.get('token_cert_label', '')
                if not library:
                    log.warning("Token PKCS#11 habilitado pero sin librería configurada")
                    return pdf_bytes
                if not pin:
                    log.warning("Token PKCS#11 habilitado pero sin PIN configurado")
                    return pdf_bytes
                log.info(f"Firmando PDF con token PKCS#11 (slot={slot})")
                return PDFSigner.sign_pdf_with_token(
                    pdf_bytes=pdf_bytes,
                    library_path=library,
                    slot=slot,
                    pin=pin,
                    cert_label=cert_label,
                    reason="Certificación de equipo biomédico",
                    location=location,
                    contact=contact,
                )
            else:
                # Firma con archivo PFX/P12
                cert_path = config.get('digital_signature_cert_path', '')
                password = config.get('digital_signature_password', '')
                if not cert_path:
                    log.debug("Firma digital habilitada pero sin certificado configurado")
                    return pdf_bytes
                if not PDFSigner.is_available():
                    log.debug("endesive no disponible, PDF sin firma digital")
                    return pdf_bytes
                return PDFSigner.sign_pdf(
                    pdf_bytes=pdf_bytes,
                    cert_path=cert_path,
                    password=password,
                    reason="Certificación de equipo biomédico",
                    location=location,
                    contact=contact,
                )
        except ImportError:
            log.debug("pdf_signer no disponible")
            return pdf_bytes
        except Exception as e:
            log.error(f"Error en firma digital: {e}")
            return pdf_bytes

    def set_logo(self, logo_path: str, company_name: Optional[str] = None):
        """
        Configurar logo y nombre de empresa.

        Args:
            logo_path: Ruta al archivo de imagen del logo
            company_name: Nombre de la empresa
        """
        if os.path.exists(logo_path):
            self.logo_path = logo_path
        else:
            log.warning(f"Logo no encontrado en {logo_path}")

        if company_name:
            self.company_name = company_name

    def set_technician(self, name: str):
        """
        Configurar nombre del técnico responsable.

        Args:
            name: Nombre del técnico
        """
        self.technician_name = name
