import os
from datetime import datetime, date, timedelta
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'app.db')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

db = SQLAlchemy(app)


class Production(db.Model):
    __tablename__ = 'production'
    id = db.Column(db.Integer, primary_key=True)
    record_date = db.Column(db.Date, nullable=False, index=True)
    eggs_count = db.Column(db.Integer, nullable=False, default=0)
    meat_kg = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.String(255), nullable=True)


class Sale(db.Model):
    __tablename__ = 'sales'
    id = db.Column(db.Integer, primary_key=True)
    record_date = db.Column(db.Date, nullable=False, index=True)
    item = db.Column(db.String(50), nullable=False)  # e.g., eggs, meat
    quantity = db.Column(db.Float, nullable=False, default=0.0)
    unit = db.Column(db.String(20), nullable=False, default='unit')
    unit_price = db.Column(db.Float, nullable=False, default=0.0)
    total_amount = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.String(255), nullable=True)


class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    record_date = db.Column(db.Date, nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.String(255), nullable=True)


def create_database() -> None:
    with app.app_context():
        db.create_all()


def parse_date(value: str) -> date:
    return datetime.strptime(value, '%Y-%m-%d').date()


def parse_decimal(value: str, default: float = 0.0) -> float:
    try:
        return float(Decimal(value))
    except (InvalidOperation, ValueError, TypeError):
        return float(default)


@app.route('/')
def dashboard():
    # Last 30 days by default
    end_date = date.today()
    start_date = end_date - timedelta(days=29)

    # Prepare date labels
    days = [(start_date + timedelta(days=i)) for i in range(30)]
    labels = [d.strftime('%Y-%m-%d') for d in days]

    # Initialize series
    sales_by_day = defaultdict(float)
    expenses_by_day = defaultdict(float)
    eggs_by_day = defaultdict(int)
    meat_by_day = defaultdict(float)

    # Aggregate Sales
    sales_rows = (
        db.session.query(Sale.record_date, db.func.sum(Sale.total_amount))
        .filter(Sale.record_date >= start_date, Sale.record_date <= end_date)
        .group_by(Sale.record_date)
        .all()
    )
    for rd, total in sales_rows:
        sales_by_day[rd.strftime('%Y-%m-%d')] = float(total or 0.0)

    # Aggregate Expenses
    expense_rows = (
        db.session.query(Expense.record_date, db.func.sum(Expense.amount))
        .filter(Expense.record_date >= start_date, Expense.record_date <= end_date)
        .group_by(Expense.record_date)
        .all()
    )
    for rd, total in expense_rows:
        expenses_by_day[rd.strftime('%Y-%m-%d')] = float(total or 0.0)

    # Aggregate Production
    prod_rows = (
        db.session.query(
            Production.record_date,
            db.func.sum(Production.eggs_count),
            db.func.sum(Production.meat_kg),
        )
        .filter(Production.record_date >= start_date, Production.record_date <= end_date)
        .group_by(Production.record_date)
        .all()
    )
    for rd, eggs_sum, meat_sum in prod_rows:
        eggs_by_day[rd.strftime('%Y-%m-%d')] = int(eggs_sum or 0)
        meat_by_day[rd.strftime('%Y-%m-%d')] = float(meat_sum or 0.0)

    sales_series = [round(sales_by_day[d], 2) for d in labels]
    expenses_series = [round(expenses_by_day[d], 2) for d in labels]
    eggs_series = [int(eggs_by_day[d]) for d in labels]
    meat_series = [round(meat_by_day[d], 2) for d in labels]

    # Totals
    total_sales = round(sum(sales_series), 2)
    total_expenses = round(sum(expenses_series), 2)
    total_eggs = int(sum(eggs_series))
    total_meat = round(sum(meat_series), 2)

    return render_template(
        'index.html',
        labels=labels,
        sales_series=sales_series,
        expenses_series=expenses_series,
        eggs_series=eggs_series,
        meat_series=meat_series,
        total_sales=total_sales,
        total_expenses=total_expenses,
        total_eggs=total_eggs,
        total_meat=total_meat,
    )


@app.route('/production')
def production_list():
    rows = Production.query.order_by(Production.record_date.desc(), Production.id.desc()).all()
    return render_template('production_list.html', rows=rows)


@app.route('/sales')
def sales_list():
    rows = Sale.query.order_by(Sale.record_date.desc(), Sale.id.desc()).all()
    return render_template('sales_list.html', rows=rows)


@app.route('/expenses')
def expenses_list():
    rows = Expense.query.order_by(Expense.record_date.desc(), Expense.id.desc()).all()
    return render_template('expenses_list.html', rows=rows)


@app.route('/production/new', methods=['GET', 'POST'])
def production_new():
    if request.method == 'POST':
        try:
            record_date = parse_date(request.form.get('record_date'))
        except Exception:
            record_date = date.today()

        eggs_count = int(parse_decimal(request.form.get('eggs_count') or '0'))
        meat_kg = parse_decimal(request.form.get('meat_kg') or '0')
        notes = (request.form.get('notes') or '').strip() or None

        if eggs_count < 0:
            eggs_count = 0
        if meat_kg < 0:
            meat_kg = 0.0

        entry = Production(
            record_date=record_date,
            eggs_count=eggs_count,
            meat_kg=meat_kg,
            notes=notes,
        )
        db.session.add(entry)
        db.session.commit()
        return redirect(url_for('production_list'))

    return render_template('production_form.html')


@app.route('/sales/new', methods=['GET', 'POST'])
def sales_new():
    if request.method == 'POST':
        try:
            record_date = parse_date(request.form.get('record_date'))
        except Exception:
            record_date = date.today()

        item = (request.form.get('item') or 'eggs').strip() or 'eggs'
        quantity = parse_decimal(request.form.get('quantity') or '0')
        unit = (request.form.get('unit') or 'unit').strip() or 'unit'
        unit_price = parse_decimal(request.form.get('unit_price') or '0')
        total_amount = parse_decimal(request.form.get('total_amount') or '0')
        notes = (request.form.get('notes') or '').strip() or None

        if total_amount <= 0 and unit_price > 0 and quantity > 0:
            total_amount = unit_price * quantity

        total_amount = max(0.0, total_amount)

        entry = Sale(
            record_date=record_date,
            item=item,
            quantity=quantity,
            unit=unit,
            unit_price=unit_price,
            total_amount=total_amount,
            notes=notes,
        )
        db.session.add(entry)
        db.session.commit()
        return redirect(url_for('sales_list'))

    return render_template('sales_form.html')


@app.route('/expenses/new', methods=['GET', 'POST'])
def expenses_new():
    if request.method == 'POST':
        try:
            record_date = parse_date(request.form.get('record_date'))
        except Exception:
            record_date = date.today()

        category = (request.form.get('category') or 'feed').strip() or 'misc'
        amount = parse_decimal(request.form.get('amount') or '0')
        notes = (request.form.get('notes') or '').strip() or None

        amount = max(0.0, amount)

        entry = Expense(
            record_date=record_date,
            category=category,
            amount=amount,
            notes=notes,
        )
        db.session.add(entry)
        db.session.commit()
        return redirect(url_for('expenses_list'))

    return render_template('expenses_form.html')


if __name__ == '__main__':
    create_database()
    app.run(host='0.0.0.0', port=5000, debug=True)