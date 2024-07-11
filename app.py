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
    if pd.notnull(row['Tone']) and pd.isnull(row['TSQ']):
        tone = f"{row['Tone']}"
        if '.' not in tone:
            tone += '.0'
        return 'Tone', f"{tone}Hz"
    elif pd.notnull(row['Tone']) and pd.notnull(row['TSQ']):
        tsq = f"{row['TSQ']}"
        if '.' not in tsq:
            tsq += '.0'
        return 'TSQL', f"{tsq}Hz"
    elif row['Mode'] == 'DSTR':
        return 'OFF', '82.5Hz'
    else:
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
    output_freq_col = [col for col in df.columns if re.match(r'^\d+Output Freq$', col)][0]

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
    df[['Repeater Call', 'Gateway Call']] = df.apply(determine_callsign, axis=1, result_type="expand", output_freq_col=output_freq_col)
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
        'Latitude': df['lat'],
        'Longitude': df['long'],
        'UTC Offset': format_utc_offset(utc_offset),
        'Location': df['Location']
    })

    return final_df

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        sort_by = request.form.getlist('sort_by')
        files = request.files.getlist('files[]')

        if 'files[]' not in request.files or len(files) == 0:
            flash('No file part')
            return redirect(request.url)

        all_dfs = []

        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)

                group_no = request.form.get(f'group_no_{files.index(file)}')
                group_name = request.form.get(f'group_name_{files.index(file)}')
                utc_offset = request.form.get(f'utc_offset_{files.index(file)}')
                name_choice = request.form.get(f'name_choice_{files.index(file)}')
                position_choice = request.form.get(f'position_choice_{files.index(file)}')

                processed_df = process_csv(file_path, group_no, group_name, utc_offset, name_choice, position_choice)
                if processed_df is not None:
                    all_dfs.append(processed_df)

        if not all_dfs:
            flash("No valid CSV files were processed.")
            return redirect(request.url)

        final_df = pd.concat(all_dfs, ignore_index=True)

        print("Columns in final_df:", final_df.columns.tolist())
        print("Sort by columns:", sort_by)

        if sort_by:
            for col in sort_by:
                if col not in final_df.columns:
                    print(f"Error: Column '{col}' not found in DataFrame")
                    flash(f"Error: Column '{col}' not found in DataFrame")
                    return redirect(request.url)
            final_df = final_df.sort_values(by=sort_by)

        if request.form.get('addHotspot'):
            hotspot_designator = request.form.get('hotspot_designator')
            hotspot_repeater_call = request.form.get('hotspot_repeater_call').ljust(7) + hotspot_designator
            hotspot_gateway_call = request.form.get('hotspot_gateway_call')
            if len(hotspot_gateway_call) < 8 or hotspot_gateway_call[7] != 'G':
                flash("Error: Hotspot Gateway Call Sign must have 'G' as the 8th character.")
                return redirect(request.url)

            hotspot_offset = request.form.get('hotspot_offset')
            if hotspot_offset == 'Simplex Hotspot':
                hotspot_offset = 0.0

            hotspot_data = {
                'Group No': request.form.get('hotspot_group_no'),
                'Group Name': request.form.get('hotspot_group_name'),
                'Name': request.form.get('hotspot_name'),
                'Sub Name': request.form.get('hotspot_sub_name'),
                'Repeater Call Sign': hotspot_repeater_call,
                'Gateway Call Sign': hotspot_gateway_call,
                'Frequency': request.form.get('hotspot_frequency'),
                'Dup': 'DUP-' if request.form.get('hotspot_dup') == '-' else 'DUP+',
                'Offset': hotspot_offset,
                'Mode': 'DV',
                'TONE': 'OFF',
                'Repeater Tone': '88.5Hz',
                'RPT1USE': 'Yes',
                'Position': request.form.get('hotspot_position'),
                'Latitude': request.form.get('hotspot_latitude'),
                'Longitude': request.form.get('hotspot_longitude'),
                'UTC Offset': format_utc_offset(request.form.get('hotspot_utc_offset'))
            }
            final_df = pd.concat([final_df, pd.DataFrame([hotspot_data])], ignore_index=True)

        if 'Location' in final_df.columns:
            final_df.drop(columns=['Location'], inplace=True)
        output_file = os.path.join(app.config['OUTPUT_FOLDER'], 'repeater_list.csv')
        final_df.to_csv(output_file, index=False)
        return send_file(output_file, as_attachment=True)

    return render_template('upload.html')

if __name__ == "__main__":
    app.run(debug=True)
