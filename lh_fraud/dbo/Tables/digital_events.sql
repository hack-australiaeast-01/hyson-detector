CREATE TABLE [dbo].[digital_events] (
    [event_id]       VARCHAR (8000) NULL,
    [timestamp]      DATETIME2 (6)  NULL,
    [customer_id]    VARCHAR (8000) NULL,
    [session_id]     VARCHAR (8000) NULL,
    [event_type]     VARCHAR (8000) NULL,
    [channel]        VARCHAR (8000) NULL,
    [device_id]      VARCHAR (8000) NULL,
    [ip_country]     VARCHAR (8000) NULL,
    [auth_method]    VARCHAR (8000) NULL,
    [status]         VARCHAR (8000) NULL,
    [beneficiary_id] VARCHAR (8000) NULL
);


GO