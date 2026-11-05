CREATE TABLE [dbo].[cards] (
    [card_id]             VARCHAR (8000)  NULL,
    [customer_id]         VARCHAR (8000)  NULL,
    [card_type]           VARCHAR (8000)  NULL,
    [is_international]    BIT             NULL,
    [issue_date]          DATE            NULL,
    [expiry_date]         DATE            NULL,
    [daily_limit_tnd]     DECIMAL (12, 3) NULL,
    [atm_daily_limit_tnd] DECIMAL (12, 3) NULL,
    [contactless_enabled] BIT             NULL
);


GO