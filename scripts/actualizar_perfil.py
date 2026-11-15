import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import re
import textwrap

from collections import defaultdict
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "README.md"
CONFIG = RAIZ / "config.json"
ASSETS = RAIZ / "assets"

API = "https://api.github.com"
COLORES = [
    "#39d0a5",
    "#42b8d5",
    "#9b87f5",
    "#f0b35a",
    "#e879a8",
    "#82c26b",
]

TOKEN = os.getenv("PROFILE_TOKEN", "").strip()

def consultar_api(url, datos=None):
    if not TOKEN:
        raise RuntimeError(
            "No se encontró la variable PROFILE_TOKEN."
        )

    cuerpo = (
        json.dumps(datos).encode("utf-8")
        if datos is not None
        else None
    )

    peticion = urllib.request.Request(
        url,
        data=cuerpo,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "perfil-github-personal",
        },
        method="POST" if datos is not None else "GET",
    )

    try:
        with urllib.request.urlopen(
            peticion, timeout=30
        ) as respuesta:
            return json.load(respuesta)

    except urllib.error.HTTPError as error:
        detalle = error.read().decode(
            "utf-8", errors="replace"
        )
        raise RuntimeError(
            f"Error HTTP {error.code} de GitHub: {detalle}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"No fue posible conectar con GitHub: {error.reason}"
        ) from error

def obtener_repositorios(usuario):
    repositorios = []
    pagina = 1

    while True:
        ruta = urllib.parse.quote(usuario, safe="")
        url = (
            f"{API}/users/{ruta}/repos"
            f"?per_page=100&page={pagina}&type=owner"
        )

        resultado = consultar_api(url)

        if not resultado:
            break

        repositorios.extend(resultado)

        if len(resultado) < 100:
            break

        pagina += 1

    return repositorios

def obtener_lenguajes(repositorios):
    totales = defaultdict(int)

    for repositorio in repositorios:
        nombre = urllib.parse.quote(
            repositorio["full_name"],
            safe="/",
        )

        datos = consultar_api(
            f"{API}/repos/{nombre}/languages"
        )

        for lenguaje, cantidad in datos.items():
            totales[lenguaje] += cantidad

    return dict(totales)

def obtener_contribuciones(usuario):
    hoy = datetime.now(timezone.utc).date()
    inicio = date(hoy.year, 1, 1)

    consulta = """
    query($usuario: String!, $inicio: DateTime!, $fin: DateTime!) {
      user(login: $usuario) {
        contributionsCollection(from: $inicio, to: $fin) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
                weekday
              }
            }
          }
        }
      }
    }
    """

    variables = {
        "usuario": usuario,
        "inicio": f"{inicio.isoformat()}T00:00:00Z",
        "fin": datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds"),
    }

    respuesta = consultar_api(
        f"{API}/graphql",
        {
            "query": consulta,
            "variables": variables,
        },
    )

    if respuesta.get("errors"):
        raise RuntimeError(
            "Error consultando contribuciones: "
            + json.dumps(
                respuesta["errors"],
                ensure_ascii=False,
            )
        )

    usuario_info = respuesta.get("data", {}).get("user")

    if not usuario_info:
        raise RuntimeError(
            f"No se encontró el usuario {usuario}."
        )

    calendario = usuario_info[
        "contributionsCollection"
    ]["contributionCalendar"]

    dias = [
        dia
        for semana in calendario["weeks"]
        for dia in semana["contributionDays"]
        if inicio.isoformat()
        <= dia["date"]
        <= hoy.isoformat()
    ]

    return calendario["totalContributions"], dias

def crear_svg(titulo, contenido, alto=190, ancho=900):
    return f"""<svg xmlns="http://www.w3.org/2000/svg"
  width="{ancho}" height="{alto}"
  viewBox="0 0 {ancho} {alto}"
  role="img" aria-label="{escape(titulo, quote=True)}">

<style>
  .fondo {{ fill: #101820; }}
  .tarjeta {{
    fill: #17232d;
    stroke: #29404d;
  }}
  .titulo {{
    fill: #39d0a5;
    font: bold 19px monospace;
  }}
  .valor {{
    fill: #e6edf3;
    font: bold 31px monospace;
  }}
  .texto {{
    fill: #a7b7c4;
    font: 13px monospace;
  }}

  @media (prefers-color-scheme: light) {{
    .fondo {{ fill: #ffffff; }}
    .tarjeta {{
      fill: #f4f8fa;
      stroke: #d7e2e8;
    }}
    .valor {{ fill: #17212b; }}
    .texto {{ fill: #526371; }}
  }}
</style>

<rect class="fondo"
  width="{ancho}" height="{alto}" rx="14"/>

<text class="titulo" x="28" y="35">
  {escape(titulo)}
</text>

{contenido}

</svg>
"""


def guardar_svg(nombre, contenido):
    destino = ASSETS / nombre
    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    destino.write_text(
        contenido,
        encoding="utf-8",
    )

    print(f"SVG generado: {destino.relative_to(ASSETS)}")

def generar_estadisticas(repositorios, contribuciones):
    ahora = datetime.now(timezone.utc)
    fecha_actualizacion = ahora.strftime("%d/%m/%Y %H:%M UTC")
    anio = ahora.year

    estrellas = sum(
        repo["stargazers_count"]
        for repo in repositorios
    )

    datos = [
        ("Repositorios públicos", len(repositorios)),
        ("Estrellas recibidas", estrellas),
        (f"Contribuciones en {anio}", contribuciones),
    ]

    elementos = []

    for indice, (etiqueta, valor) in enumerate(datos):
        x = 28 + indice * 285

        elementos.extend([
            f'<rect class="tarjeta" x="{x}" y="55" '
            'width="260" height="105" rx="10"/>',

            f'<text class="valor" x="{x + 18}" '
            f'y="105">{valor:,}</text>',

            f'<text class="texto" x="{x + 18}" '
            f'y="135">{escape(etiqueta)}</text>',
        ])

    elementos.append(
        '<text class="texto" x="28" y="185">'
        f'Actualizado: {fecha_actualizacion}'
        '</text>'
    )

    guardar_svg(
        "estadisticas.svg",
        crear_svg(
            "Resumen de actividad en GitHub",
            "\n".join(elementos),
            alto=215,
        ),
    )

def generar_lenguajes(lenguajes, maximo):
    total = sum(lenguajes.values())

    if total == 0:
        return False

    ordenados = sorted(
        lenguajes.items(),
        key=lambda elemento: elemento[1],
        reverse=True,
    )[:maximo]

    elementos = []

    for indice, (nombre, cantidad) in enumerate(ordenados):
        porcentaje = cantidad / total * 100
        ancho_barra = max(2, 560 * porcentaje / 100)
        y = 60 + indice * 32
        color = COLORES[indice % len(COLORES)]

        elementos.extend([
            f'<text class="texto" x="28" y="{y + 14}">'
            f'{escape(nombre)}</text>',

            f'<rect x="190" y="{y}" '
            'width="560" height="17" rx="5" '
            'fill="#263944"/>',

            f'<rect x="190" y="{y}" '
            f'width="{ancho_barra:.1f}" height="17" '
            f'rx="5" fill="{color}"/>',

            f'<text class="texto" x="775" y="{y + 14}">'
            f'{porcentaje:.1f}%</text>',
        ])

    alto = 75 + len(ordenados) * 32

    guardar_svg(
        "lenguajes.svg",
        crear_svg(
            "Distribución de lenguajes",
            "\n".join(elementos),
            alto=alto,
        ),
    )

    return True

def generar_contribuciones(dias, anio):
    if not dias:
        guardar_svg(
            "contribuciones.svg",
            crear_svg(
                f"Contribuciones de {anio}",
                '<text class="texto" x="28" y="85">'
                "Sin actividad registrada.</text>",
            ),
        )
        return

    primera_fecha = date.fromisoformat(dias[0]["date"])
    primer_domingo = primera_fecha.toordinal() - (
        (primera_fecha.weekday() + 1) % 7
    )

    elementos = []
    maximo = max(
        (dia["contributionCount"] for dia in dias),
        default=0,
    ) or 1

    for dia in dias:
        fecha = date.fromisoformat(dia["date"])
        diferencia = fecha.toordinal() - primer_domingo
        columna = diferencia // 7
        fila = (fecha.weekday() + 1) % 7

        cantidad = dia["contributionCount"]
        intensidad = cantidad / maximo

        if cantidad == 0:
            color = "#263944"
        elif intensidad < 0.25:
            color = "#1c806d"
        elif intensidad < 0.50:
            color = "#27a987"
        elif intensidad < 0.75:
            color = "#39d0a5"
        else:
            color = "#8ce8cf"

        x = 32 + columna * 15
        y = 60 + fila * 15

        elementos.append(
            f'<rect x="{x}" y="{y}" width="12" '
            f'height="12" rx="2" fill="{color}"/>'
        )

    ultima_fecha = date.fromisoformat(dias[-1]["date"])
    semanas = (
        (ultima_fecha.toordinal() - primer_domingo) // 7
    ) + 1

    ancho = max(900, 60 + semanas * 15)

    guardar_svg(
        "contribuciones.svg",
        crear_svg(
            f"Calendario de contribuciones · {anio}",
            "\n".join(elementos),
            alto=185,
            ancho=ancho,
        ),
    )

def formatear_fecha_github(valor):
    """Convierte una fecha ISO de GitHub a DD/MM/AAAA."""
    if not valor:
        return "Sin registros"

    fecha = datetime.fromisoformat(
        valor.replace("Z", "+00:00")
    )

    return fecha.strftime("%d/%m/%Y")

def generar_tarjeta_proyecto(repo, nombre_archivo):
    """Genera una tarjeta SVG individual para un repositorio."""

    nombre = repo["name"]
    descripcion = (
        repo.get("description")
        or "Proyecto personal en desarrollo."
    )

    lenguaje = repo.get("language") or "Sin especificar"
    estrellas = repo.get("stargazers_count", 0)

    ultimo_push = formatear_fecha_github(
        repo.get("pushed_at")
    )

    nombre_visible = textwrap.shorten(
        nombre,
        width=31,
        placeholder="...",
    )

    descripcion = " ".join(descripcion.split())

    lineas = textwrap.wrap(
        descripcion,
        width=51,
        max_lines=2,
        placeholder="...",
        break_long_words=True,
    )

    while len(lineas) < 2:
        lineas.append("")

    contenido = f"""
    <rect class="tarjeta"
      x="14" y="52" width="872" height="145"
      rx="12"/>

    <!-- Nombre del repositorio -->
    <text class="titulo" x="35" y="83">
      &gt; {escape(nombre_visible)}
    </text>

    <!-- Descripción -->
    <text class="texto" x="35" y="111">
      {escape(lineas[0])}
    </text>

    <text class="texto" x="35" y="130">
      {escape(lineas[1])}
    </text>

    <!-- Separador -->
    <line x1="35" y1="145" x2="865" y2="145"
      stroke="#29404d" stroke-width="1"/>

    <!-- Metadatos -->
    <text x="35" y="171"
      fill="#42b8d5"
      font-family="monospace"
      font-size="14">
      {escape(lenguaje[:24])}
    </text>

    <text x="285" y="171"
      fill="#f0b35a"
      font-family="monospace"
      font-size="14">
      ★ {estrellas}
    </text>

    <text class="texto" x="500" y="171">
      Último push: {ultimo_push}
    </text>
    """

    guardar_svg(
        nombre_archivo,
        crear_svg(
            "Proyecto destacado",
            contenido,
            alto=212,
        ),
    )


def generar_tarjetas_proyectos(repositorios, destacados):
    """
    Genera tarjetas de proyectos en assets/proyectos
    y devuelve el HTML para insertarlas en el README.
    """

    directorio = ASSETS / "proyectos"
    directorio.mkdir(parents=True, exist_ok=True)

    disponibles = {
        repo["name"].casefold(): repo
        for repo in repositorios
    }

    tarjetas = []
    archivos_generados = set()

    for nombre in destacados:
        repo = disponibles.get(nombre.casefold())

        if repo is None:
            print(
                f"Advertencia: no se encontró el proyecto {nombre}"
            )
            continue

        slug = re.sub(
            r"[^a-z0-9_-]+",
            "-",
            repo["name"].lower(),
        ).strip("-")

        import hashlib
        identificador = hashlib.sha256(
            repo["name"].encode("utf-8")
        ).hexdigest()[:8]

        archivo = f"{slug}-{identificador}.svg"
        destino = directorio / archivo

        generar_tarjeta_proyecto(
            repo,
            f"proyectos/{archivo}",
        )

        archivos_generados.add(destino.name)

        url = escape(
            repo["html_url"],
            quote=True,
        )

        titulo = escape(
            repo["name"],
            quote=True,
        )

        tarjetas.append(
            '<td width="50%" align="center" valign="top">'
            f'<a href="{url}">'
            f'<img src="./assets/proyectos/{archivo}" '
            f'alt="Proyecto {titulo}" width="100%"/>'
            '</a>'
            '</td>'
        )

    for archivo in directorio.glob("*.svg"):
        if archivo.name not in archivos_generados:
            archivo.unlink()

    if not tarjetas:
        return "No hay proyectos destacados disponibles."

    filas = []

    for indice in range(0, len(tarjetas), 2):
        columnas = tarjetas[indice:indice + 2]

        if len(columnas) == 1:
            columnas.append('<td width="50%"></td>')

        filas.append(
            "<tr>\n"
            + "\n".join(columnas)
            + "\n</tr>"
        )

    return (
        '<table width="100%">\n'
        + "\n".join(filas)
        + "\n</table>"
    )

def reemplazar_seccion(texto, nombre, contenido):
    inicio = f"<!-- {nombre}:INICIO -->"
    fin = f"<!-- {nombre}:FIN -->"

    if texto.count(inicio) != 1 or texto.count(fin) != 1:
        raise ValueError(
            f"Marcadores inválidos para {nombre}."
        )

    anterior, resto = texto.split(inicio, 1)
    _, posterior = resto.split(fin, 1)

    return (
        f"{anterior}{inicio}\n"
        f"{contenido}\n"
        f"{fin}{posterior}"
    )

def actualizar_readme(repositorios, destacados, hay_lenguajes):
    texto = README.read_text(encoding="utf-8")

    bloques = {
        "LENGUAJES": (
            '<div align="center">\n'
            '<img src="./assets/lenguajes.svg" '
            'alt="Lenguajes de programación" width="100%">\n'
            "</div>"
            if hay_lenguajes
            else "Todavía no hay datos de lenguajes."
        ),
        "ESTADISTICAS": (
            '<div align="center">\n'
            '<img src="./assets/estadisticas.svg" '
            'alt="Estadísticas de GitHub" width="100%">\n'
            "</div>"
        ),        
        "PROYECTOS": generar_tarjetas_proyectos(
            repositorios,
            destacados,
        ),
        "CONTRIBUCIONES": (
            '<div align="center">\n'
            '<img src="./assets/contribuciones.svg" '
            'alt="Calendario de contribuciones" width="100%">\n'
            "</div>"
        ),
    }

    for nombre, contenido in bloques.items():
        texto = reemplazar_seccion(
            texto, nombre, contenido
        )

    README.write_text(texto, encoding="utf-8")


# ---------------------------------------
# Ejecución
# ---------------------------------------

def main():
    configuracion = json.loads(
        CONFIG.read_text(encoding="utf-8")
    )

    usuario = configuracion["usuario"]

    print(f"Consultando perfil de {usuario}...")

    repositorios = obtener_repositorios(usuario)

    if configuracion.get("excluir_forks", True):
        repositorios = [
            repo for repo in repositorios
            if not repo["fork"]
        ]

    lenguajes = obtener_lenguajes(repositorios)

    contribuciones, dias = obtener_contribuciones(usuario)

    generar_estadisticas(
        repositorios, contribuciones
    )

    hay_lenguajes = generar_lenguajes(
        lenguajes,
        configuracion.get("maximo_lenguajes", 6),
    )

    generar_contribuciones(
        dias,
        datetime.now(timezone.utc).year,
    )

    actualizar_readme(
        repositorios,
        configuracion["proyectos_destacados"],
        hay_lenguajes,
    )

    print("README actualizado correctamente.")

if __name__ == "__main__":
    try:
        main()
    except (
        RuntimeError,
        ValueError,
        KeyError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)