import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

function getSeqId(val) {
    if (typeof val === "number") return val;
    if (Array.isArray(val)) return val[0];
    if (val && typeof val === "object") return val.id;
    return null;
}

function sequenceNext(seq) {
    const now = new Date();
    const pad = (n, w) => String(n).padStart(w, "0");
    const dict = {
        year: now.getFullYear(),
        month: pad(now.getMonth() + 1, 2),
        day: pad(now.getDate(), 2),
        y: String(now.getFullYear()).slice(-2),
        h12: pad(now.getHours() % 12 || 12, 2),
    };
    const fmt = (s) => (s || "").replace(/%\((\w+)\)s/g, (_, k) => String(dict[k] ?? ""));
    const num = seq.number_next_actual;
    seq.number_next_actual += seq.number_increment;
    return fmt(seq.prefix) + pad(num, seq.padding) + fmt(seq.suffix);
}

patch(PosStore.prototype, {
    async initServerData() {
        await super.initServerData();
        const config = this.config;
        const feId = getSeqId(config.FE_sequence_id);
        const teId = getSeqId(config.TE_sequence_id);
        if (feId && teId) {
            const sequences = await this.data.orm.read(
                "ir.sequence",
                [feId, teId],
                ["name", "prefix", "suffix", "padding", "number_next_actual", "number_increment"]
            );
            this.FE_sequence = sequences.find((s) => s.id === feId);
            this.TE_sequence = sequences.find((s) => s.id === teId);
        }
    },

    pushSingleOrder(order) {
        const partner = order.partner_id;
        if (partner?.vat) {
            order.sequence = this.FE_sequence?.number_next_actual ?? null;
            order.number_electronic = this.FE_sequence ? sequenceNext(this.FE_sequence) : null;
            order.tipo_documento = "FE";
        } else {
            order.sequence = this.TE_sequence?.number_next_actual ?? null;
            order.number_electronic = this.TE_sequence ? sequenceNext(this.TE_sequence) : null;
            order.tipo_documento = "TE";
        }
        return super.pushSingleOrder(order);
    },
});

patch(PosOrder.prototype, {
    setup(vals) {
        super.setup(vals);
        this.sequence = vals.sequence ?? null;
        this.number_electronic = vals.number_electronic ?? null;
        this.tipo_documento = vals.tipo_documento ?? null;
    },

    serializeForORM(opts = {}) {
        const data = super.serializeForORM(opts);
        if (this.number_electronic) {
            data.sequence = this.sequence;
            data.number_electronic = this.number_electronic;
            data.tipo_documento = this.tipo_documento;
        }
        return data;
    },
});
