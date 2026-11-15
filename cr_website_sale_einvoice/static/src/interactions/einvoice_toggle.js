import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';

/**
 * Turning the electronic invoice off takes effect right away (the order goes back to an electronic
 * ticket), so the page never shows the switch off while the order still asks for the invoice.
 * Turning it on only shows the data fields: the customer saves them with the form's button.
 */
export class EinvoiceToggle extends Interaction {
    static selector = '.o_cr_einvoice_form';
    dynamicContent = {
        '#cr_einvoice_requested': { 't-on-change': this.onToggle },
    };

    onToggle(ev) {
        if (!ev.currentTarget.checked) {
            this.el.submit();
        }
    }
}

registry
    .category('public.interactions')
    .add('cr_website_sale_einvoice.einvoice_toggle', EinvoiceToggle);
