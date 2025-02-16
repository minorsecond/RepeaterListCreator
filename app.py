import os
import re
import pandas as pd
from flask import Flask, request, render_template, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'output'
app.config['ALLOWED_EXTENSIONS'] = {'csv'}

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['OUTPUT_FOLDER']):
    os.makedirs(app.config['OUTPUT_FOLDER'])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def format_utc_offset(offset):
    # Return the offset string directly
    return offset

def determine_tone(row):
    def process_csv(file_path, group_no, group_name, utc_offset, name_choice, position_choice):
        df = pd.read_csv(file_path)
        df = clean_columns(df)
        # output_freq_col = [col for col in df.columns if re.match(r'^\d+Output Freq$', col)][0]
        output_freq_col = next((col for col in df.columns if "Output Freq" in col), None)

        if output_freq_col is None:
            raise ValueError("No matching column found for 'Output Freq'")

        print(f"Processing file: {file_path}")
        print("Initial columns:", df.columns.tolist())

        df['Mode'] = df['Mode'].str.strip()
        df.loc[df['Mode'].str.contains('analog', case=False), 'Mode'] = 'analog'
        df = df[df['Mode'].isin(['analog', 'DSTR'])]

        if name_choice == 'Location':
            if 'Location' not in df.columns:
                print("Error: 'Location' column not found in CSV")
                flash(f"Error: 'Location' column not found in {file_path}")
                return None
            df['Name'] = df['Location']
        else:
            df['Name'] = df[output_freq_col]

        df['Dup'] = df['Offset'].apply(lambda x: 'DUP-' if x == '-' else 'DUP+')
        df['Offset'] = (df[output_freq_col] - df['Input Freq']).abs().round(1)

        df[['TONE', 'Repeater Tone']] = df.apply(determine_tone, axis=1, result_type="expand")
        df[['Repeater Call', 'Gateway Call']] = df.apply(lambda row: determine_callsign(row, output_freq_col), axis=1,
                                                         result_type="expand")
        df['Mode'] = df['Mode'].apply(lambda x: 'FM' if x == 'analog' else 'DV')

        final_df = pd.DataFrame({
            'Group No': group_no,
            'Group Name': group_name,
            'Name': df['Name'],
            'Sub Name': '',
            'Repeater Call Sign': df['Repeater Call'],
            'Gateway Call Sign': df['Gateway Call'],
            'Frequency': df[output_freq_col],
            'Dup': df['Dup'],
            'Offset': df['Offset'],
            'Mode': df['Mode'],
            'TONE': df['TONE'],
            'Repeater Tone': df['Repeater Tone'],
            'RPT1USE': 'Yes',
            'Position': position_choice,
            'Latitude': df['Lat'],
            'Longitude': df['Long'],
            'UTC Offset': format_utc_offset(utc_offset),
            'Location': df['Location']
        })

    if pd.notnull(row['Uplink Tone']):
        tone = str(row['Uplink Tone']).strip()

        # If it's a regular tone, ensure it ends with ".0" for consistency
        if tone.replace('.', '', 1).isdigit():  # Check if it's numeric
            if '.' not in tone:
                tone += '.0'
            return 'Tone', f"{tone}Hz"

        # If it's a digital tone (D023, etc.), return it as TSQL
        return 'TSQL', tone

    elif row['Mode'] == 'DSTR':  # Default digital mode tone
        return 'OFF', '82.5Hz'

    return '', ''

def determine_callsign(row, output_freq_col):
    if row['Mode'] == 'analog':
        return row['Call'], ''
    else:
        band = float(row[output_freq_col])
        padded_call = row['Call'].ljust(7)
        if 144 <= band <= 148:
            return f"{padded_call}C", f"{padded_call}G"
        elif 420 <= band <= 450:
            return f"{padded_call}B", f"{padded_call}G"
        else:
            return row['Call'], f"{padded_call}G"

def process_csv(file_path, group_no, group_name, utc_offset, name_choice, position_choice):
    df = pd.read_csv(file_path)
    df = clean_columns(df)
    #output_freq_col = [col for col in df.columns if re.match(r'^\d+Output Freq$', col)][0]
    output_freq_col = next((col for col in df.columns if "Output Freq" in col), None)

    if output_freq_col is None:
        raise ValueError("No matching column found for 'Output Freq'")


    print(f"Processing file: {file_path}")
    print("Initial columns:", df.columns.tolist())

    df['Mode'] = df['Mode'].str.strip()
    df.loc[df['Mode'].str.contains('analog', case=False), 'Mode'] = 'analog'
    df = df[df['Mode'].isin(['analog', 'DSTR'])]

    if name_choice == 'Location':
        if 'Location' not in df.columns:
            print("Error: 'Location' column not found in CSV")
            flash(f"Error: 'Location' column not found in {file_path}")
            return None
        df['Name'] = df['Location']
    else:
        df['Name'] = df[output_freq_col]

    df['Dup'] = df['Offset'].apply(lambda x: 'DUP-' if x == '-' else 'DUP+')
    df['Offset'] = (df[output_freq_col] - df['Input Freq']).abs().round(1)

    df[['TONE', 'Repeater Tone']] = df.apply(determine_tone, axis=1, result_type="expand")
    df[['Repeater Call', 'Gateway Call']] = df.apply(lambda row: determine_callsign(row, output_freq_col), axis=1, result_type="expand")
    df['Mode'] = df['Mode'].apply(lambda x: 'FM' if x == 'analog' else 'DV')

    final_df = pd.DataFrame({
        'Group No': group_no,
        'Group Name': group_name,
        'Name': df['Name'],
        'Sub Name': '',
        'Repeater Call Sign': df['Repeater Call'],
        'Gateway Call Sign': df['Gateway Call'],
        'Frequency': df[output_freq_col],
        'Dup': df['Dup'],
        'Offset': df['Offset'],
        'Mode': df['Mode'],
        'TONE': df['TONE'],
        'Repeater Tone': df['Repeater Tone'],
        'RPT1USE': 'Yes',
        'Position': position_choice,
        'Latitude': df['Lat'],
        'Longitude': df['Long'],
        'UTC Offset': format_utc_offset(utc_offset),
        'Location': df['Location']
    })

    return final_df


@app.route("/", methods=["GET", "POST"])
def upload_file():
    if request.method == "POST":
        if "files[]" not in request.files:
            flash("No file part")
            return redirect(request.url)

        files = request.files.getlist("files[]")

        # User-specified column names
        column_mappings = {
            "frequency": request.form.get("col_frequency"),
            "location": request.form.get("col_location"),
            "name": request.form.get("col_name"),
            "tone": request.form.get("col_tone"),
            "tone_type": request.form.get("col_tone_type"),
            "offset": request.form.get("col_offset"),
            "input_frequency": request.form.get("col_input_frequency"),
            "mode": request.form.get("col_mode"),
            "latitude": request.form.get("col_latitude"),
            "longitude": request.form.get("col_longitude")
        }

        for key, col_name in column_mappings.items():
            if not col_name:
                flash(f"You must specify a column for {key}.")
                return redirect(request.url)

        all_data = []

        for file in files:
            if file.filename == "":
                flash("No selected file")
                return redirect(request.url)

            file_path = os.path.join(UPLOAD_FOLDER, file.filename)
            file.save(file_path)

            try:
                df = pd.read_csv(file_path)
                missing_cols = [col for col in column_mappings.values() if col not in df.columns]
                if missing_cols:
                    flash(f"The file {file.filename} is missing columns: {', '.join(missing_cols)}")
                    return redirect(request.url)

                df = df[list(column_mappings.values())]
                df.rename(columns={v: k for k, v in column_mappings.items()}, inplace=True)
                all_data.append(df)

            except Exception as e:
                flash(f"Error processing {file.filename}: {str(e)}")
                return redirect(request.url)

        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            output_path = os.path.join(UPLOAD_FOLDER, "processed_output.csv")
            final_df.to_csv(output_path, index=False)
            flash("File successfully processed!", "success")
            return redirect(request.url)

    return render_template("upload.html")


if __name__ == "__main__":
    app.run(debug=True)
