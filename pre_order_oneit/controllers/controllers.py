# -*- coding: utf-8 -*-
from odoo import http

# class PreOrderOneit(http.Controller):
#     @http.route('/pre_order_oneit/pre_order_oneit/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/pre_order_oneit/pre_order_oneit/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('pre_order_oneit.listing', {
#             'root': '/pre_order_oneit/pre_order_oneit',
#             'objects': http.request.env['pre_order_oneit.pre_order_oneit'].search([]),
#         })

#     @http.route('/pre_order_oneit/pre_order_oneit/objects/<model("pre_order_oneit.pre_order_oneit"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('pre_order_oneit.object', {
#             'object': obj
#         })