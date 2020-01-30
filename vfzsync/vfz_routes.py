from flask import Flask, render_template, jsonify
from vfzsync import app
import vfzsync.vfz_flask as vfz_flask


@app.route('/api/sync/run')
def vfzsync():
    return jsonify(vfz_flask.run_sync())


@app.route('/home')
def home():
    return render_template('home.html')


@app.route('/')
@app.route('/sync')
def sync():
    return render_template('sync.html')
