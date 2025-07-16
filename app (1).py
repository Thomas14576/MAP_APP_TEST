
# Streamlit App: KML Viewer from Google My Maps URL with Export and Visual Embed

import streamlit as st
import zipfile
import os
import shutil
import xml.etree.ElementTree as ET
from xml.dom.minidom import Document
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import re
import requests

# --- Setup ---
st.set_page_config(layout="wide")
st.title("Google My Maps to SVG Exporter")

shutil.rmtree("svg_layers", ignore_errors=True)
os.makedirs("svg_layers", exist_ok=True)

# --- Step 1: Enter Google My Maps URL ---
input_url = st.text_input("Paste your Google My Maps URL")

if input_url:
    match = re.search(r"mid=([^&]+)", input_url)
    if not match:
        st.error("Invalid URL: couldn't extract map ID.")
    else:
        map_id = match.group(1)
        kml_download_url = f"https://www.google.com/maps/d/kml?mid={map_id}"

        # --- Step 2: Show Live Map in Iframe ---
        st.markdown("### Live Map Preview (Google My Maps)")
        iframe_url = f"https://www.google.com/maps/d/embed?mid={map_id}"
        st.components.v1.iframe(iframe_url, height=400)

        # --- Step 3: Download KMZ File ---
        try:
            response = requests.get(kml_download_url)
            response.raise_for_status()
            kmz_filename = "downloaded_map.kmz"
            with open(kmz_filename, "wb") as f:
                f.write(response.content)
        except:
            st.error("Failed to download KMZ. Check if your map is public.")
            st.stop()

        # --- Step 4: Extract KML ---
        kml_filename = None
        with zipfile.ZipFile(kmz_filename, 'r') as kmz:
            for name in kmz.namelist():
                if name.endswith('.kml'):
                    kml_filename = name
                    kmz.extract(name, path=".")
                    break

        if not kml_filename:
            st.error("No KML file found in KMZ.")
            st.stop()

        # --- Step 5: Parse KML ---
        tree = ET.parse(kml_filename)
        root = tree.getroot()
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}

        folders = root.findall('.//kml:Folder', ns)
        all_coords = []
        folder_coords = {}

        for folder in folders:
            folder_name_elem = folder.find('kml:name', ns)
            folder_name = folder_name_elem.text.strip() if folder_name_elem is not None else 'Unnamed'
            coords = []

            for placemark in folder.findall('.//kml:Placemark', ns):
                for point in placemark.findall('.//kml:Point', ns):
                    coord_text = point.find('.//kml:coordinates', ns).text.strip()
                    lon, lat, *_ = map(float, coord_text.split(','))
                    coords.append((lon, lat))
                    all_coords.append((lon, lat))

            if coords:
                folder_coords[folder_name] = coords

        if not all_coords:
            st.error("No coordinates found in KML.")
            st.stop()

        # --- Step 6: Manual Zoom/Pan Sliders ---
        lons, lats = zip(*all_coords)
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        center_lon = (min_lon + max_lon) / 2
        center_lat = (min_lat + max_lat) / 2

        st.sidebar.header("Zoom & Pan Controls")
        zoom = st.sidebar.slider("Zoom Level (higher = closer)", min_value=1, max_value=20, value=5)
        pan_lat = st.sidebar.slider("Center Latitude", min_lat, max_lat, center_lat)
        pan_lon = st.sidebar.slider("Center Longitude", min_lon, max_lon, center_lon)

        zoom_range = 1.0 / zoom
        view_min_lat = pan_lat - zoom_range
        view_max_lat = pan_lat + zoom_range
        view_min_lon = pan_lon - zoom_range
        view_max_lon = pan_lon + zoom_range

        selected_folders = st.multiselect("Select folders to display/export", options=list(folder_coords.keys()), default=list(folder_coords.keys()))

        fig, ax = plt.subplots()

        for folder_name in selected_folders:
            coords = folder_coords[folder_name]
            visible_coords = [(lon, lat) for lon, lat in coords if view_min_lon < lon < view_max_lon and view_min_lat < lat < view_max_lat]
            if visible_coords:
                xs, ys = zip(*visible_coords)
                ax.scatter(xs, ys, label=folder_name, s=10)

        ax.set_xlim(view_min_lon, view_max_lon)
        ax.set_ylim(view_min_lat, view_max_lat)
        ax.set_title("Export Preview")
        ax.legend()
        st.pyplot(fig)

        # --- Step 7: Export SVGs ---
        def normalize_coords(lon, lat, width=1000, height=1000):
            x = (lon - view_min_lon) / (view_max_lon - view_min_lon) * width
            y = height - (lat - view_min_lat) / (view_max_lat - view_min_lat) * height
            return x, y

        for folder_name in selected_folders:
            coords = folder_coords[folder_name]
            visible_coords = [(lon, lat) for lon, lat in coords if view_min_lon < lon < view_max_lon and view_min_lat < lat < view_max_lat]
            norm_coords = [normalize_coords(lon, lat) for lon, lat in visible_coords]

            doc = Document()
            svg = doc.createElement('svg')
            svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
            svg.setAttribute('width', '1000')
            svg.setAttribute('height', '1000')
            doc.appendChild(svg)

            for x, y in norm_coords:
                circle = doc.createElement('circle')
                circle.setAttribute('cx', str(x))
                circle.setAttribute('cy', str(y))
                circle.setAttribute('r', '5')
                circle.setAttribute('fill', 'red')
                svg.appendChild(circle)

            safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', folder_name)
            filename = f"svg_layers/{safe_name}.svg"
            with open(filename, "w") as f:
                f.write(doc.toprettyxml())

        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for svg_file in os.listdir("svg_layers"):
                path = os.path.join("svg_layers", svg_file)
                zipf.write(path, svg_file)

        st.download_button(
            label="Download SVG ZIP",
            data=zip_buf.getvalue(),
            file_name="svg_layers_export.zip",
            mime="application/zip"
        )
