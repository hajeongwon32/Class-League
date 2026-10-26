"""API 묶음 (Flask Blueprint). app.py가 BLUEPRINTS를 차례로 앱에 붙인다."""

from classleague.routes import admin, auth, demo, leagues, live, matches, notes, reports

BLUEPRINTS = [auth.bp, leagues.bp, matches.bp, admin.bp, reports.bp, notes.bp, live.bp, demo.bp]
