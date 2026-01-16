"""
Wishlist Routes - Endpoints para gerenciar lista de desejos
"""
from flask import Blueprint, jsonify, request, Response
from flask_login import current_user, login_required
from db import *
import titles
import csv
from io import StringIO

wishlist_bp = Blueprint('wishlist', __name__, url_prefix='/api')

@wishlist_bp.route('/wishlist')
@login_required
def get_wishlist():
    """Obtém lista de wishlist do usuário logado"""
    from constants import APP_TYPE_BASE
    
    items = Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.priority.desc()).all()
    
    result = []
    
    for item in items:
        # Verificar se usuário possui o jogo na biblioteca
        owned = False
        app_entry = Apps.query.filter_by(
            title_id=item.title_id,
            app_type=APP_TYPE_BASE,
            owned=True
        ).first()
        
        if app_entry:
            owned = True
        
        # Obter informações do título
        title_info = titles.get_game_info(item.title_id) or {}
        
        result.append({
            'id': item.id,
            'title_id': item.title_id,
            'name': title_info.get('name', f'Unknown ({item.title_id})'),
            'priority': item.priority,
            'added_date': item.added_date.isoformat() if item.added_date else None,
            'owned': owned
        })
    
    return jsonify(result)

@wishlist_bp.route('/wishlist', methods=['POST'])
@login_required
def add_to_wishlist():
    """Adiciona jogo à wishlist"""
    data = request.json
    title_id = data.get('title_id')
    
    if not title_id:
        return jsonify({'success': False, 'error': 'title_id é obrigatório'}), 400
    
    existing = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id).first()
    if existing:
        return jsonify({'success': False, 'error': 'Jogo já está na wishlist'}), 400
    
    priority = data.get('priority', 0)
    priority = max(0, min(5, priority))
    
    item = Wishlist(
        user_id=current_user.id,
        title_id=title_id,
        priority=priority
    )
    db.session.add(item)
    db.session.commit()
    
    return jsonify({'success': True})

@wishlist_bp.route('/wishlist/<title_id>', methods=['PUT'])
@login_required
def update_wishlist_item(title_id):
    """Atualiza prioridade de um item da wishlist"""
    data = request.json
    priority = data.get('priority', 0)
    priority = max(0, min(5, priority))
    
    item = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id).first()
    if not item:
        return jsonify({'success': False, 'error': 'Item não encontrado'}), 404
    
    item.priority = priority
    db.session.commit()
    
    return jsonify({'success': True})

@wishlist_bp.route('/wishlist/<title_id>', methods=['DELETE'])
@login_required
def remove_from_wishlist(title_id):
    """Remove item da wishlist"""
    item = Wishlist.query.filter_by(user_id=current_user.id, title_id=title_id).first()
    if not item:
        return jsonify({'success': False, 'error': 'Item não encontrado'}), 404
    
    db.session.delete(item)
    db.session.commit()
    
    return jsonify({'success': True})

@wishlist_bp.route('/wishlist/export')
@login_required
def export_wishlist():
    """Exporta wishlist em json, csv ou html"""
    try:
        format_type = request.args.get('format', 'json')
        
        items = Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.priority.desc()).all()
        
        if format_type == 'json':
            result = []
            for item in items:
                title_info = titles.get_game_info(item.title_id) or {}
                result.append({
                    'title_id': item.title_id,
                    'name': title_info.get('name', 'Unknown'),
                    'priority': item.priority,
                    'added_date': item.added_date.isoformat() if item.added_date else None
                })
            return jsonify(result)
        
        elif format_type == 'csv':
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(['title_id', 'name', 'priority', 'added_date'])
            for item in items:
                title_info = titles.get_game_info(item.title_id) or {}
                writer.writerow([
                    item.title_id,
                    title_info.get('name', 'Unknown'),
                    item.priority,
                    item.added_date.isoformat() if item.added_date else ''
                ])
            return Response(
                output.getvalue(),
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=wishlist.csv'}
            )
        
        elif format_type == 'html':
            html = '<html><head><title>Wishlist Export</title></head><body>'
            html += '<h1>Wishlist</h1>'
            html += '<table border="1"><tr><th>Title ID</th><th>Name</th><th>Priority</th><th>Added Date</th></tr>'
            for item in items:
                title_info = titles.get_game_info(item.title_id) or {}
                html += f'<tr><td>{item.title_id}</td><td>{title_info.get("name", "Unknown")}</td>'
                html += f'<td>{item.priority}</td><td>{item.added_date}</td></tr>'
            html += '</table></body></html>'
            return Response(html, mimetype='text/html')
        
        return jsonify({'error': 'Formato não suportado. Use json, csv ou html'}), 400
    except Exception as e:
        import logging
        logger = logging.getLogger('main')
        logger.error(f"Error exporting wishlist: {e}")
        return jsonify({'error': str(e)}), 500


@wishlist_bp.route('/wishlist/ignore/<title_id>', methods=['POST'])
@login_required
def set_wishlist_ignore(title_id):
    """Define preferências de ignore para um item da wishlist"""
    data = request.json or {}
    ignore_dlc = data.get('ignore_dlc', False)
    ignore_update = data.get('ignore_update', False)
    
    # Buscar ou criar registro de ignore
    ignore_record = WishlistIgnore.query.filter_by(
        user_id=current_user.id, 
        title_id=title_id
    ).first()
    
    if ignore_record:
        ignore_record.ignore_dlc = ignore_dlc
        ignore_record.ignore_update = ignore_update
    else:
        ignore_record = WishlistIgnore(
            user_id=current_user.id,
            title_id=title_id,
            ignore_dlc=ignore_dlc,
            ignore_update=ignore_update
        )
        db.session.add(ignore_record)
    
    db.session.commit()
    
    return jsonify({'success': True})


@wishlist_bp.route('/wishlist/ignore/<title_id>')
@login_required
def get_wishlist_ignore(title_id):
    """Obtém preferências de ignore para um item da wishlist"""
    ignore_record = WishlistIgnore.query.filter_by(
        user_id=current_user.id, 
        title_id=title_id
    ).first()
    
    if ignore_record:
        return jsonify({
            'success': True,
            'ignore_dlc': ignore_record.ignore_dlc,
            'ignore_update': ignore_record.ignore_update
        })
    else:
        return jsonify({
            'success': True,
            'ignore_dlc': False,
            'ignore_update': False
        })


@wishlist_bp.route('/wishlist/ignore')
@login_required
def get_all_wishlist_ignore():
    """Obtém todas as preferências de ignore do usuário"""
    ignore_records = WishlistIgnore.query.filter_by(user_id=current_user.id).all()
    
    result = {}
    for record in ignore_records:
        result[record.title_id] = {
            'ignore_dlc': record.ignore_dlc,
            'ignore_update': record.ignore_update
        }
    
    return jsonify(result)
