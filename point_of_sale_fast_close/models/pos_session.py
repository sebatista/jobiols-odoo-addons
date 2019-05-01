# -*- coding: utf-8 -*-
# For copyright and license notices, see __manifest__.py file in module root

from odoo import api, fields, models, SUPERUSER_ID, _
from odoo.exceptions import UserError, ValidationError
import logging

logger = logging.getLogger(__name__)


class PosSessionToClose(models.Model):
    _name = 'pos.session.to.close'

    session_id = fields.Many2one(
        'pos.session'
    )
    step = fields.Integer(
        default=1
    )
    phase = fields.Char(
        default='bank'
    )


class PosSession(models.Model):
    _inherit = 'pos.session'

    @api.multi
    def action_pos_session_closing_control(self):
        """ Esto sobreescribe el metodo que se llama desde el boton de cerrar
            la sesion.
            Si tengo cash control llama al super y termina, o sea anda
            como antes.
            Si no lo tengo, cierro la sesion y la almaceno en la cola de
            sesiones a procesar.
        """
        # si tengo cash control tiene funcionamiento standard
        for session in self:
            if session.config_id.cash_control:
                super(PosSession, self).action_pos_session_closing_control()

        # chequear que el POS tenga un Sale Journal
            company_id = session.config_id.journal_id.company_id.id
            journal_id = self.env['ir.config_parameter'].sudo().get_param(
                'pos.closing.journal_id_%s' % company_id,
                default=session.config_id.journal_id.id)
            if not journal_id:
                raise UserError(
                    _("You have to set a Sale Journal for the POS:%s") % (
                        session.config_id.name,))

        # no tengo cash control solo cierra y prepara proceso batch
        self._check_pos_session_balance()
        for session in self:
            session.write(
                {'state': 'closed',
                 'stop_at': fields.Datetime.now()}
            )

            # guardar la sesion en la cola para procesarla luego
            sq_obj = self.env['pos.session.to.close']
            sq_obj.create({'session_id': session.id})

    @api.multi
    def post_entries(self):
        """ Llamado desde cron para procesar en background una sesion, que esta
            almacenada en PosSessionToClose.

            Cada elemento representa una sesion a cerrar, y tiene phase indica
            que cosa estamos haciendo y step que incrementa cada vez que pasa
            hasta que termina.

        """

        sq_obj = self.env['pos.session.to.close']
        pstc = sq_obj.search([], limit=1)

        if pstc:
            logger.info(
                'POS processing %s Phase %s Step %s' % (
                    pstc.session_id.name, pstc.phase, pstc.step))

            company_id = pstc.session_id.config_id.company_id.id
            ctx = dict(self.env.context, force_company=company_id,
                       company_id=company_id)

            # ejecutar la fase banco
            if pstc.phase == 'bank':
                print('ejecutando fase banco')
                for st in pstc.session_id.statement_ids:
                    st.with_context(ctx).button_confirm_bank_stepped(pstc)

            # ejecutar la fase ordenes
            if pstc.phase == 'orders':
                print('ejecutando fase ordenes')
                pstc.session_id.with_context(ctx)._confirm_orders_stepped(pstc)

    def _confirm_orders_stepped(self, pstc):
        """ hace lo mismo que _confirm_orders pero por pasos
        """
        import wdb;wdb.set_trace()

        for session in self:
            company_id = session.config_id.journal_id.company_id.id

            # traerse las ordenes en estado pago (y algo mas)
            orders = session.order_ids.filtered(
                lambda order: order.state == 'paid')

            # quedarse con las primeras tres
            orders = orders[:3]

            journal_id = self.env['ir.config_parameter'].sudo().get_param(
                'pos.closing.journal_id_%s' % company_id,
                default=session.config_id.journal_id.id)

            move = self.env['pos.order'].with_context(
                force_company=company_id)._create_account_move(
                session.start_at, session.name, int(journal_id), company_id)
            orders.with_context(
                force_company=company_id)._create_account_move_line(session,
                                                                    move)
            for order in session.order_ids.filtered(
                lambda o: o.state not in ['done', 'invoiced']):
                if order.state not in ('paid'):
                    raise UserError(
                        _(
                            "You cannot confirm all orders of this session, because they have not the 'paid' status.\n"
                            "{reference} is in state {state}, total amount: {total}, paid: {paid}").format(
                            reference=order.pos_reference or order.name,
                            state=order.state,
                            total=order.amount_total,
                            paid=order.amount_paid,
                        ))
                order.action_pos_order_done()
            orders_to_reconcile = session.order_ids._filtered_for_reconciliation()
            orders_to_reconcile.sudo()._reconcile_payments()
