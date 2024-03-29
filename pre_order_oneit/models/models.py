# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.addons import decimal_precision as dp
import xlrd
import tempfile
import binascii
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta
from random import randint

class TableOrder(models.Model):
	_name="table.pre.order"
	_description ="Tabla de productos de la Pre Orden"

	name = fields.Text(string='Description', required=True)
	product_qty = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True, default=1)
	product_uom = fields.Many2one('uom.uom', string='Product Unit of Measure', required=True)
	product_id = fields.Many2one('product.product', string='Product', domain=[('purchase_ok', '=', True)], change_default=True, required=True)
	product_type = fields.Selection(related='product_id.type', readonly=True)
	price_unit = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'))
	taxes_id = fields.Many2many('account.tax', string='Taxes', domain=['|', ('active', '=', False), ('active', '=', True)])
	price_subtotal = fields.Monetary(compute='_compute_amount', string='Subtotal', store=True)
	price_total = fields.Monetary(compute='_compute_amount', string='Total', store=True)
	pre_order_id = fields.Many2one("pre.order.purchase", ondelete='cascade')
	partner_id = fields.Many2one(related="pre_order_id.partner_id", store=True, string="Partner")

	currency_id = fields.Many2one(related='pre_order_id.currency_id', store=True, string='Currency', readonly=True)


	@api.onchange('product_id')
	def onchange_product_id(self):
		result = {}
		if not self.product_id:
			return result

		self.price_unit = self.product_qty = 0.0
		self.product_uom = self.product_id.uom_po_id or self.product_id.uom_id
		result['domain'] = {'product_uom': [('category_id', '=', self.product_id.uom_id.category_id.id)]}

		product_lang = self.product_id.with_context(
			lang=self.partner_id.lang,
			partner_id=self.partner_id.id,
		)
		self.name = product_lang.display_name
		if product_lang.description_purchase:
			self.name += '\n' + product_lang.description_purchase


		return result


	@api.depends('product_qty', 'price_unit', 'taxes_id')
	def _compute_amount(self):
		for line in self:
			vals = line._prepare_compute_all_values()
			taxes = line.taxes_id.compute_all(
				vals['price_unit'],
				vals['currency_id'],
				vals['product_qty'],
				vals['product'],
				vals['partner'])
			line.update({
				'price_total': taxes['total_included'],
				'price_subtotal': taxes['total_excluded'],
			})

	def _prepare_compute_all_values(self):
		# Hook method to returns the different argument values for the
		# compute_all method, due to the fact that discounts mechanism
		# is not implemented yet on the purchase orders.
		# This method should disappear as soon as this feature is
		# also introduced like in the sales module.
		self.ensure_one()
		return {
			'price_unit': self.price_unit,
			'currency_id': self.pre_order_id.currency_id,
			'product_qty': self.product_qty,
			'product': self.product_id,
			'partner': self.pre_order_id.partner_id,
		}

class TableProducts(models.Model):
	_name = "table.product.temp"
	_description = "Tabla de productos a cargar"

	@api.model
	def _default_sale_taxes(self):
		return 	self.env['account.tax'].search([('name', '=', ['IVA(16%) VENTAS'])]).ids


	name = fields.Char(string="Descripción")
	type = fields.Selection([('consu','Consumible'),('service','Servicio'),('product','Almacenable')], default="product", string="Tipo")
	categoria = fields.Many2one("product.category",string="Categoria")
	referencia = fields.Char(string="Referencia Interna")
	barcode = fields.Char(string="Codigo de barras")
	list_price = fields.Float(string="Precio de venta")
	standard_price = fields.Float(string="Precio de compra")
	# marca = fields.Char(string="Marca")
	# modelo = fields.Char(string="Modelo")
	taxes_id = fields.Many2many("account.tax", string="Impuestos Cliente", default=_default_sale_taxes)
	#taxes_pro_id = fields.Many2many("account.tax", string="Impuestos Proveedor", default=lambda self: self.env['account.tax'].search([('name', '=', ['IVA(16%) COMPRAS'])]).ids)
	route_ids = fields.Many2many("stock.location.route", string="Rutas de entrega", default=lambda self: self.env['stock.location.route'].search([('name', 'in', ['Comprar','Bajo pedido'])]).ids)
	product_id = fields.Many2one("product.product", string="Producto")
	is_minor = fields.Char(string='minor')
	pre_order_id = fields.Many2one("pre.order.purchase", ondelete='cascade')


class PreOrderONEIT(models.Model):
	_name = "pre.order.purchase"
	_description = "Registro de Pre Orden"

	name = fields.Char(string="Name", readonly=True)
	partner_id = fields.Many2one("res.partner",string="Cliente", required=True)
	fecha = fields.Datetime(string="Fecha", required=True, default=fields.datetime.now())
	archivo = fields.Binary(string="Archivo Excel")
	currency_id = fields.Many2one('res.currency', 'Currency', required=True,
		default=lambda self: self.env.user.company_id.currency_id.id)
	filename = fields.Char('File Name')

	order_id = fields.Many2one("sale.order", string="Orden Relacionada")

	pre_product_ids = fields.One2many("table.product.temp","pre_order_id",string="Productos")
	pre_order_ids = fields.One2many("table.pre.order","pre_order_id",string="Lineas de pedido")

	# @api.multi
	# def create_sale_lines(self):

	@api.model
	def create(self, values):
		pso = super(PreOrderONEIT, self).create(values)
		sequence = self.env['ir.sequence'].search([('name','=','Pre Order Sequence')], limit=1)
		pso.name = sequence.next_by_id()
		return pso

	@api.multi
	def create_sale_order(self):
		for rec in self:
			so=self.env['sale.order'].create({
			'name': self.env['ir.sequence'].next_by_code('sale.order') or _('New'),
			'partner_id':rec.partner_id.id,
			'date_order':rec.fecha,
			'origin':rec.name,
			'currency_id':rec.currency_id,
			})
			rec.order_id = so.id

			for x in rec.pre_order_ids:
				self.env['sale.order.line'].create({
				'product_id': x.product_id.id,
				'product_uom': x.product_id.uom_id.id,
				'name': x.product_id.name,
				'price_unit': x.price_unit,
				'product_uom_qty':x.product_qty,
				'order_id': so.id
				})


	@api.multi
	def create_update_products(self):
		for rec in self:
			for x in rec.pre_product_ids:
				if x.is_minor == 'F':
					if not x.product_id:
						taxes = []
						for t in x.taxes_id:
							taxes.append(t.id)
						routes = []
						for r in x.route_ids:
							routes.append(r.id)
						vals = {
							'name':x.name,
							'type':x.type,
							'categ_id':x.categoria.id,
							'default_code':x.referencia,
							'barcode':x.barcode,
							'list_price':x.list_price,
							'standard_price':x.standard_price,
							'taxes_id':[(6, 0, taxes)],
							'route_ids':[(6, 0, routes)],
							'tracking':'serial',
							}
						pro = self.env['product.product'].create(vals)
						x.product_id = pro.id
						print("Template del producto: ", x.product_id.product_tmpl_id.id)
						print("****** Valores 1 " + str(vals))
						sup = self.env['res.partner'].search([('name','=','Proveedor Pendiente')], limit=1)
						supp = x.product_id.seller_ids.create({
							'name': sup.id,
							'product_tmpl_id': pro.product_tmpl_id.id,
							'min_qty': 1,
							'price':pro.standard_price,
							})
					if x.product_id:
						taxes = []
						for t in x.taxes_id:
							taxes.append(t.id)
						routes = []
						for r in x.route_ids:
							routes.append(r.id)
						x.product_id.name = x.name
						x.product_id.type = x.type
						x.product_id.categ_id = x.categoria.id
						x.product_id.default_code = x.referencia
						x.product_id.barcode = x.barcode
						x.product_id.list_price = x.list_price
						x.product_id.standard_price = x.standard_price
						x.product_id.taxes_id = [(6, 0, taxes)]
						x.product_id.route_ids = [(6, 0, routes)]
						x.product_id.tracking = 'serial'
				else:
					if not x.product_id:
						taxes = []
						for t in x.taxes_id:
							taxes.append(t.id)
						routes = []
						for r in x.route_ids:
							routes.append(r.id)
						vals = {
							'name':x.name,
							'type':x.type,
							'categ_id':x.categoria.id,
							'default_code':x.referencia,
							'barcode':x.barcode,
							'list_price':x.list_price,
							'standard_price':x.standard_price,
							'taxes_id':[(6, 0, taxes)],
							'route_ids':[(6, 0, routes)],
							'tracking':'none'
							}
						pro = self.env['product.product'].create(vals)
						x.product_id = pro.id
						print("Template del producto: ", x.product_id.product_tmpl_id.id)
						print("****** Valores 2 " + str(vals))
						sup = self.env['res.partner'].search([('name','=','Proveedor Pendiente')], limit=1)
						supp = x.product_id.seller_ids.create({
							'name': sup.id,
							'product_tmpl_id': pro.product_tmpl_id.id,
							'min_qty': 1,
							'price':pro.standard_price,
							})
					if x.product_id:
						taxes = []
						for t in x.taxes_id:
							taxes.append(t.id)
						routes = []
						for r in x.route_ids:
							routes.append(r.id)
						x.product_id.name = x.name
						x.product_id.type = x.type
						x.product_id.categ_id = x.categoria.id
						x.product_id.default_code = x.referencia
						x.product_id.barcode = x.barcode
						x.product_id.list_price = x.list_price
						x.product_id.standard_price = x.standard_price
						x.product_id.taxes_id = [(6, 0, taxes)]
						x.product_id.route_ids = [(6, 0, routes)]
						x.product_id.tracking = 'none'
						

	@api.multi
	def charge_products(self):
		for rec in self:
			for x in rec.pre_order_ids:
				x.unlink()
			fp = tempfile.NamedTemporaryFile(suffix=".xlsx")
			fp.write(binascii.a2b_base64(rec.archivo))
			fp.seek(0)
			workbook = xlrd.open_workbook(fp.name)
			sheet = workbook.sheet_by_index(0)
			for row_no in range(sheet.nrows):
				if row_no <= 0:
					fields = map(lambda row:row.value.encode('utf-8'), sheet.row(row_no))
				else:
					line = list(map(lambda row:isinstance(row.value, str) and row.value.encode('utf-8') or str(row.value), sheet.row(row_no)))
					# print ("==========",str(line[2]))
					pro = self.env['product.product']
					pro_temp = self.env['product.template']
					r = str(line[4])
					m = str(line[0])
					if pro_temp.search([('name','=',r[2:-1])], limit=1):
						pro_temp = self.env['product.template'].search([('name','=',r[2:-1])], limit = 1)
						producto = pro.search([('product_tmpl_id','=',pro_temp.id)], limit=1)
						rec.pre_order_ids.create({
							'product_id': producto.id,
							'product_type':producto.type,
							'product_qty':line[5],
							'product_uom':producto.uom_id.id,
							'price_unit':producto.list_price,
							'name':pro_temp.name,
							'taxes_id':[(6, 0, producto.taxes_id.ids)],
						
							'pre_order_id': rec.id,
							
					
							})
					else:
						raise ValidationError(
							_('El producto ' +str(line[4])+ ' no ha sido creado'))

	@api.multi
	def products_temp_view(self):
		for rec in self:
			for x in rec.pre_product_ids:
				x.unlink()
			fp = tempfile.NamedTemporaryFile(suffix=".xlsx")
			fp.write(binascii.a2b_base64(rec.archivo))
			fp.seek(0)
			workbook = xlrd.open_workbook(fp.name)
			sheet = workbook.sheet_by_index(0)
			for row_no in range(sheet.nrows):
				if row_no <= 0:
					fields = map(lambda row:row.value.encode('utf-8'), sheet.row(row_no))
				else:
					line = list(map(lambda row:isinstance(row.value, str) and row.value.encode('utf-8') or str(row.value), sheet.row(row_no)))
					# print ("==========",str(line[2]))  # in this line variable you get the value line by line from excel.
					cat_id = False
					cat = self.env['product.category']
					pro = self.env['product.product']
					pro_temp = self.env['product.template']
					c = str(line[2])
					r = str(line[4])
					m = str(line[0])
					if pro_temp.search([('name','=',r[2:-1])], limit=1):
						p_temp = pro_temp.search([('name','=',r[2:-1])], limit=1)
						p = pro.search([('product_tmpl_id','=',p_temp.id)], limit=1)
						self.pre_product_ids.create({
						'name': p.name,
						'referencia': p.default_code,
						'barcode': p.barcode,
						'categoria': p.categ_id.id,
						'list_price': p.list_price,
						'standard_price': p.standard_price,
						'taxes_id':[(6, 0, p.taxes_id.ids)],
						'route_ids':[(6, 0, p.route_ids.ids)],
						'pre_order_id': rec.id,
						'is_minor':m[2:-1],
						'product_id': p.id,
						})
					else:
						barcode_gen = randint(0, 700000) + randint(0, 900000)
						pref_name = str(line[4][0:3])
						barcode_format = str(pref_name[2:-1]) + "-" + str(barcode_gen)
						if cat.search([('name','=',c[2:-1])], limit=1):
							cat_id = cat.search([('name','=',c[2:-1])], limit=1)
						else:
							cat_id = cat.create({
								'name': c[2:-1],
								'property_cost_method':'standard',
								'property_valuation':'manual_periodic'
								})
						search_temp = self.env['table.product.temp'].search([('barcode','=',barcode_format)], limit = 1)
						if search_temp:
							barcode_gen = randint(0, 700000) + randint(0, 900000)
							pref_name = str(line[4][0:3])
							barcode_format = str(pref_name[2:-1]) + "-" + str(barcode_gen)
						self.pre_product_ids.create({
						'name': line[4],
						'referencia': line[3],
						'barcode': barcode_format,
						'categoria': cat_id.id,
						'list_price': float(line[7]),
						'standard_price': float(line[6]),
						'is_minor':m[2:-1],
						'pre_order_id': rec.id,

						})