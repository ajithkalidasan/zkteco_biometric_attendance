/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class MonthlyCalendar extends Component {
    setup() {
        this.orm = useService("orm");
        
        const now = new Date();
        this.state = useState({
            year: now.getFullYear(),
            month: now.getMonth() + 1,
            department_id: false,
            data: null,
            loading: true,
            activeTab: 'attendance'
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.loading = true;
        try {
            this.state.data = await this.orm.call(
                "zk.attendance.dashboard", 
                "get_monthly_calendar_data", 
                [this.state.year, this.state.month, this.state.department_id]
            );
        } finally {
            this.state.loading = false;
        }
    }

    async onPrevMonth() {
        if (this.state.month === 1) {
            this.state.month = 12;
            this.state.year--;
        } else {
            this.state.month--;
        }
        await this.loadData();
    }

    async onNextMonth() {
        if (this.state.month === 12) {
            this.state.month = 1;
            this.state.year++;
        } else {
            this.state.month++;
        }
        await this.loadData();
    }

    async onToday() {
        const now = new Date();
        this.state.year = now.getFullYear();
        this.state.month = now.getMonth() + 1;
        await this.loadData();
    }

    async onDeptChange(ev) {
        const val = ev.target.value;
        this.state.department_id = val ? parseInt(val) : false;
        await this.loadData();
    }

    onTabClick(tab) {
        this.state.activeTab = tab;
    }

    async onToday() {
        const now = new Date();
        this.state.year = now.getFullYear();
        this.state.month = now.getMonth() + 1;
        await this.loadData();
    }

    get todayIso() {
        const d = new Date();
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    }
}

MonthlyCalendar.template = "smr_zk_attendace.MonthlyCalendar";
registry.category("actions").add("smr_zk_attendace.monthly_calendar", MonthlyCalendar);
