# 用户使用指南 (USER_GUIDE)

## 1. 打开桌面程序
双击 `OmanAllowanceApp.exe`。

## 2. 切换语言（中文 / English）
在窗口顶部语言下拉框中选择 **中文** 或 **English**。
- 语言设置会自动保存
- 影响界面显示与导出表头

## 3. 主页（Dashboard）与月度结算
### 3.1 选择结算月份
- 在 **结算月份** 中选择 `YYYY-MM`

### 3.2 本月特殊发放（重要）
面板标题：**本月特殊发放**
- 只列出本月可操作的特殊项目
- 包含：
  - 毕业行李补助（未发放过的毕业生）
  - 退学当月生活补助（仅退学月份）

勾选后点击 **运行结算**。

### 3.3 运行结算
点击 **运行结算** 后：
- 系统生成当月结算记录
- 显示 run_id、汇率、配置版本

## 4. 学生管理
### 4.1 新增/编辑/删除
在 **学生** 标签页：
- 新增：点击 **新增**
- 编辑：选中学生 → **编辑**
- 删除：选中学生 → **删除**（会弹出确认）

### 4.2 批量导入（CSV）
点击 **导入**，选择 CSV 文件。

CSV 列要求：
- student_id, name, degree_level, first_entry_date, status, graduation_date, withdrawal_date

### 4.3 CSV 模板
点击 **下载 CSV 模板**。

## 5. 配置（Config）
在 **配置** 标签页设置：
- 生活补助（USD）
- 学习补助（USD）
- 行李补助（USD）
- 汇率（USD→CNY）
- 政策开关（入境年 10 月前毕业/退学）
- 退学当月生活补助默认发放

点击 **保存配置**。

## 6. 结算结果（Reports）
在 **结算结果** 标签页查看：
- 学生合计（CNY）
- 明细记录（含 rule_id、description、metadata）

### 导出
- 点击 **导出 CSV** 或 **导出 Excel**
- 金额为 CNY 两位小数
- 包含 run_id、settlement_month、fx_rate

## 7. 备份与恢复
在 **备份/恢复** 标签页：
- 一键备份：生成 ZIP 备份
- 恢复：支持 **替换** 或 **合并**
- 恢复前会自动生成备份

## 8. 典型流程（推荐）
1. 在 **配置** 中更新汇率与补助标准
2. 在 **学生** 中导入或维护名单
3. 在 **仪表盘** 选择结算月份并确认“本月特殊发放”
4. 运行结算
5. 在 **结算结果** 导出 CSV/XLSX

## 9. 示例数据
示例文件：`demo/demo_students.csv`

## 10. 截图占位
- Dashboard 截图：待补充
- Special Payments 截图：待补充
- Reports 截图：待补充

---

# USER GUIDE (English)

## 1. Launch the Desktop App
Double-click `OmanAllowanceApp.exe`.

## 2. Switch Language (中文 / English)
Use the language dropdown at the top.
- The selection is saved
- It affects UI text and export headers

## 3. Dashboard and Monthly Settlement
### 3.1 Select Settlement Month
- Choose `YYYY-MM` in **Settlement month**

### 3.2 Special Payments This Month (Important)
Panel title: **Special Payments This Month**
- Only shows eligible items
- Includes:
  - Baggage allowance (graduated and not paid)
  - Living allowance in withdrawal month

Select checkboxes and click **Run settlement**.

### 3.3 Run Settlement
After running:
- A monthly run is created
- Run ID, FX rate, and config version are shown

## 4. Students
### 4.1 Add/Edit/Delete
In **Students** tab:
- Add: **Add**
- Edit: select row → **Edit**
- Delete: select row → **Delete** (confirmation required)

### 4.2 Bulk Import (CSV)
Click **Import CSV** and select a file.

Required columns:
- student_id, name, degree_level, first_entry_date, status, graduation_date, withdrawal_date

### 4.3 CSV Template
Click **Download CSV template**.

## 5. Config
In **Config** tab set:
- Living allowance (USD)
- Study allowance (USD)
- Baggage allowance (USD)
- FX rate (USD→CNY)
- Policy switch (exit before October in entry year)
- Default pay living allowance in withdrawal month

Click **Save config**.

## 6. Settlement Results
In **Settlement Results** tab:
- Per-student totals (CNY)
- Record lines with rule_id/description/metadata

### Export
- **Export CSV** or **Export Excel**
- Amounts in CNY (2 decimals)
- Includes run_id, settlement_month, fx_rate

## 7. Backup & Restore
In **Backup/Restore** tab:
- Create backup ZIP
- Restore: Replace or Merge
- Pre-restore backup is created automatically

## 8. Typical Workflow
1. Update allowances and FX in **Config**
2. Import or maintain students
3. Choose settlement month and review **Special Payments This Month**
4. Run settlement
5. Export CSV/XLSX

## 9. Demo Data
Sample file: `demo/demo_students.csv`

## 10. Screenshot Placeholders
- Dashboard screenshot: TBD
- Special Payments screenshot: TBD
- Reports screenshot: TBD
