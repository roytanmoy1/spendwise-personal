import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react';

const request = fetchBaseQuery({ baseUrl: '/graphql', credentials: 'include' });
const refreshRequest = fetchBaseQuery({ baseUrl: '/', credentials: 'include' });
let refreshInFlight;
let sessionGeneration = 0;

function refreshSession(api, extraOptions) {
  if (!refreshInFlight) {
    refreshInFlight = refreshRequest(
      { url: '/auth/refresh', method: 'POST' }, api, extraOptions,
    ).finally(() => { refreshInFlight = undefined; });
  }
  return refreshInFlight;
}

export async function graphqlBaseQuery({ query, variables }, api, extraOptions) {
  const requestGeneration = sessionGeneration;
  const requestArgs = { url: '', method: 'POST', body: { query, variables } };
  let result = await request(requestArgs, api, extraOptions);
  const graphqlErrors = result.data?.errors || [];
  const needsRefresh = result.error?.status === 401 || graphqlErrors.some(({ message }) =>
    message === 'Sign in to continue' || message === 'Verify your email to continue');
  if (needsRefresh) {
    const refreshed = requestGeneration !== sessionGeneration
      ? { error: undefined }
      : await refreshSession(api, extraOptions);
    if (!refreshed.error && requestGeneration === sessionGeneration) sessionGeneration += 1;
    if (!refreshed.error) result = await request(requestArgs, api, extraOptions);
  }
  if (result.error) return { error: { status: result.error.status, message: 'Unable to connect to SpendWise' } };
  if (result.data?.errors?.length) {
    const message = result.data.errors[0].message;
    return { error: { status: ['Sign in to continue', 'Verify your email to continue'].includes(message) ? 401 : 400, message } };
  }
  return { data: result.data?.data };
}

export const spendwiseApi = createApi({
  reducerPath: 'spendwiseApi',
  baseQuery: graphqlBaseQuery,
  tagTypes: ['Viewer', 'Overview', 'Transactions', 'Budgets'],
  endpoints: (builder) => ({
    getViewer: builder.query({
      query: () => ({ query: '{ viewer { id name email persona role status emailVerified } }' }),
      transformResponse: (response) => response.viewer,
      providesTags: ['Viewer'],
    }),
    getOverview: builder.query({
      query: () => ({ query: `{
        overview { totalSpentMinor thisMonthMinor lastMonthMinor transactionCount
          byCategory { category amountMinor } byMethod { method amountMinor }
          monthly { month amountMinor } byCity { city amountMinor } }
      }` }),
      transformResponse: (response) => response.overview,
      providesTags: ['Overview'],
    }),
    getTransactions: builder.query({
      query: ({ limit = 25, offset = 0, filter = null } = {}) => ({
        query: `query Transactions($limit: Int!, $offset: Int!, $filter: TransactionFilter) {
          transactions(limit: $limit, offset: $offset, filter: $filter) {
            totalCount hasMore items {
              id merchant amountMinor category method occurredAt city note source
            }
          }
        }`, variables: { limit, offset, filter },
      }),
      transformResponse: (response) => response.transactions,
      providesTags: ['Transactions'],
    }),
    getBudgets: builder.query({
      query: (month) => ({ query: `query Budgets($month: String) {
        budgets(month: $month) { id month category limitMinor spentMinor }
      }`, variables: { month } }),
      transformResponse: (response) => response.budgets,
      providesTags: ['Budgets'],
    }),
    exportCsv: builder.query({
      query: () => ({ query: '{ exportCsv }' }),
      transformResponse: (response) => response.exportCsv,
    }),
    register: builder.mutation({
      query: (variables) => ({ query: `mutation Register($name: String!, $email: String!, $password: String!, $persona: String!) {
        register(name: $name, email: $email, password: $password, persona: $persona) {
          authenticated requiresVerification requiresPasswordSetup message viewer { id name email persona role status emailVerified }
        }
      }`, variables }),
      invalidatesTags: ['Viewer'],
    }),
    login: builder.mutation({
      query: (variables) => ({ query: `mutation Login($email: String!, $password: String!) {
        login(email: $email, password: $password) {
          authenticated requiresVerification requiresPasswordSetup requiresRegistration message viewer { id name email persona role status emailVerified }
        }
      }`, variables }),
      invalidatesTags: ['Viewer', 'Overview', 'Transactions', 'Budgets'],
    }),
    verifyEmail: builder.mutation({
      query: (variables) => ({ query: `mutation VerifyEmail($email: String!, $code: String!) {
        verifyEmail(email: $email, code: $code) { id name email persona role status emailVerified }
      }`, variables }),
      invalidatesTags: ['Viewer', 'Overview', 'Transactions', 'Budgets'],
    }),
    resendVerificationCode: builder.mutation({
      query: (email) => ({ query: 'mutation Resend($email: String!) { resendVerificationCode(email: $email) }', variables: { email } }),
    }),
    updateProfile: builder.mutation({
      query: (variables) => ({ query: `mutation UpdateProfile($name: String!, $persona: String!) {
        updateProfile(name: $name, persona: $persona) { id name email persona role status emailVerified }
      }`, variables }),
      invalidatesTags: ['Viewer'],
    }),
    getPendingUsers: builder.query({
      query: () => ({ query: '{ pendingUsers { id name email persona role status emailVerified createdAt } }' }),
      transformResponse: (response) => response.pendingUsers,
      providesTags: ['PendingUsers'],
    }),
    getManagedUsers: builder.query({
      query: () => ({ query: '{ managedUsers { id name email persona role status emailVerified createdAt } }' }),
      transformResponse: (response) => response.managedUsers,
      providesTags: ['ManagedUsers'],
    }),
    getAdminNotifications: builder.query({
      query: () => ({ query: '{ adminNotifications { id applicantEmail event createdAt read } }' }),
      transformResponse: (response) => response.adminNotifications,
      providesTags: ['AdminNotifications'],
    }),
    assignRole: builder.mutation({
      query: ({ userId, role }) => ({ query: `mutation AssignRole($userId: ID!, $role: UserRole!) {
        assignRole(userId: $userId, role: $role) { id name email persona role status emailVerified createdAt }
      }`, variables: { userId, role } }),
      invalidatesTags: ['PendingUsers', 'ManagedUsers', 'AdminNotifications'],
    }),
    createUser: builder.mutation({
      query: (variables) => ({ query: `mutation CreateUser($name: String!, $email: String!, $persona: String!) {
        createUser(name: $name, email: $email, persona: $persona) { authenticated requiresVerification message }
      }`, variables }),
      invalidatesTags: ['PendingUsers', 'ManagedUsers', 'AdminNotifications'],
    }),
    removeUser: builder.mutation({
      query: (userId) => ({ query: 'mutation RemoveUser($userId: ID!) { removeUser(userId: $userId) }', variables: { userId } }),
      invalidatesTags: ['PendingUsers', 'ManagedUsers', 'AdminNotifications'],
    }),
    markAdminNotificationRead: builder.mutation({
      query: (id) => ({ query: 'mutation MarkRead($id: ID!) { markAdminNotificationRead(id: $id) }', variables: { id } }),
      invalidatesTags: ['AdminNotifications'],
    }),
    logout: builder.mutation({
      query: () => ({ query: 'mutation { logout }' }),
      invalidatesTags: ['Viewer', 'Overview', 'Transactions', 'Budgets'],
    }),
    addTransaction: builder.mutation({
      query: (input) => ({ query: `mutation AddTransaction($input: TransactionInput!) {
        addTransaction(input: $input) { id }
      }`, variables: { input } }),
      invalidatesTags: ['Overview', 'Transactions', 'Budgets'],
    }),
    updateTransactionCategory: builder.mutation({
      query: ({ id, category }) => ({ query: `mutation Correct($id: ID!, $category: Category!) {
        updateTransactionCategory(id: $id, category: $category) { id category }
      }`, variables: { id, category } }),
      invalidatesTags: ['Overview', 'Transactions', 'Budgets'],
    }),
    deleteTransaction: builder.mutation({
      query: (id) => ({ query: 'mutation Delete($id: ID!) { deleteTransaction(id: $id) }', variables: { id } }),
      invalidatesTags: ['Overview', 'Transactions', 'Budgets'],
    }),
    importCsv: builder.mutation({
      query: (csvText) => ({ query: 'mutation Import($csv: String!) { importCsv(csvText: $csv) { imported } }', variables: { csv: csvText } }),
      invalidatesTags: ['Overview', 'Transactions', 'Budgets'],
    }),
    setBudget: builder.mutation({
      query: (input) => ({ query: `mutation Budget($input: BudgetInput!) {
        setBudget(input: $input) { id month category limitMinor spentMinor }
      }`, variables: { input } }),
      invalidatesTags: ['Budgets'],
    }),
  }),
});

export const {
  useGetViewerQuery, useGetOverviewQuery, useGetTransactionsQuery, useGetBudgetsQuery,
  useLazyExportCsvQuery, useRegisterMutation, useLoginMutation,
  useVerifyEmailMutation, useResendVerificationCodeMutation, useUpdateProfileMutation,
  useGetPendingUsersQuery, useGetManagedUsersQuery, useGetAdminNotificationsQuery, useAssignRoleMutation,
  useCreateUserMutation, useRemoveUserMutation, useMarkAdminNotificationReadMutation,
  useLogoutMutation, useAddTransactionMutation, useUpdateTransactionCategoryMutation,
  useDeleteTransactionMutation, useImportCsvMutation, useSetBudgetMutation,
} = spendwiseApi;