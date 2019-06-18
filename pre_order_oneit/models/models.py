# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.addons import decimal_precision as dp

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
	pre_order_id = fields.Many2one("pre.order.purchase")
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
			'currency_id': self.order_id.currency_id,
			'product_qty': self.product_qty,
			'product': self.product_id,
			'partner': self.order_id.partner_id,
		}


class PreOrderONEIT(models.Model):
	_name = "pre.order.purchase"
	_description = "Registro de Pre Orden"

	name = fields.Char(string="Name")
	partner_id = fields.Many2one("res.partner",string="Cliente")
	fecha = fields.Date(string="Fecha")
	archivo = fields.Binary(string="Archivo Excel")
	currency_id = fields.Many2one('res.currency', 'Currency', required=True,
		default=lambda self: self.env.user.company_id.currency_id.id)
	filename = fields.Char('File Name')
	pre_order_ids = fields.One2many("table.pre.order","pre_order_id",string="Lineas de pedido")